import eventlet
eventlet.monkey_patch()

from tweepy import OAuthHandler, API, Cursor, TweepError, RateLimitError
from textblob import TextBlob
import pandas as pd
from datetime import datetime
import time
import os
import re
import keys_token as key
from eventlet.wsgi import server as Server
import socketio
import json
from shutil import rmtree, make_archive

class SentimentAnalysis:
    tweepy_auth = OAuthHandler(key.CONSUMER_KEY, key.CONSUMER_SECRET_KEY)
    tweepy_auth.set_access_token(key.ACCESS_TOKEN, key.ACCESS_SECRET_TOKEN)
    tweepy_api = API(tweepy_auth, wait_on_rate_limit=False, wait_on_rate_limit_notify=False)

    def __init__(self, session_id):
        self.session_id = session_id
        self.polarity = {
            'positive': 0,
            'negative': 0,
            'neutral': 0
        }
        self.search_key = ''
        self.tweet_count = 0
    
    # https://stackoverflow.com/questions/4770297/convert-utc-datetime-string-to-local-datetime
    def datetime_from_utc_to_local(self, utc_datetime):
        now_timestamp = time.time()
        offset = datetime.fromtimestamp(now_timestamp) - datetime.utcfromtimestamp(
            now_timestamp)
        return utc_datetime + offset
    
    def create_directories(self):
        os.mkdir(f'./{self.session_id}')
        os.mkdir(f'./{self.session_id}/images')
        os.mkdir(f'./{self.session_id}/images/top_users')
        os.mkdir(f'./{self.session_id}/images/trends')
    
    def save_files(self, df):
        df = df.sort_values(by=['like_count', 'retweet_count', 'followers_count'], ascending=False)
        df.to_csv(path_or_buf=f'./{self.session_id}/{self.search_key}.csv')

        screen_name_df = pd.DataFrame(columns=['screen_name', 'no. of tweets'])
        screen_name_df = df['screen_name'].value_counts().rename_axis('screen_name').to_frame(name='no. of tweets')
        
        top_10_freq_users = screen_name_df.head(10)
        tweet_trend_df = df['tweet_date'].value_counts().rename_axis('date').to_frame(name='count').sort_values(by='date')
        
        screen_name_df.to_csv(path_or_buf=f'./{self.session_id}/screen_name_freq.csv')
        top_10_freq_users.plot(kind='pie', figsize=(30, 20), fontsize=26, y='no. of tweets').get_figure().savefig(f'./{self.session_id}/images/top_users/no_of_tweets.jpg')
        top_10_freq_users.plot(kind='pie', figsize=(30, 20), fontsize=26, y='no. of tweets').get_figure().savefig(f'./{self.session_id}/images/top_users/no_of_tweets.png')
        top_10_freq_users.plot(kind='pie', figsize=(30, 20), fontsize=26, y='no. of tweets').get_figure().savefig(f'./{self.session_id}/images/top_users/no_of_tweets.svg')
        top_10_freq_users.plot(kind='pie', figsize=(30, 20), fontsize=26, y='no. of tweets').get_figure().savefig(f'./{self.session_id}/images/top_users/no_of_tweets.pdf')

        tweet_trend_df.to_csv(path_or_buf=f'./{self.session_id}/trend.csv')
        tweet_trend_df.plot(kind='line', figsize=(70, 50), fontsize=26).get_figure().savefig(f'./{self.session_id}/images/trends/trend.jpg')
        tweet_trend_df.plot(kind='line', figsize=(70, 50), fontsize=26).get_figure().savefig(f'./{self.session_id}/images/trends/trend.png')
        tweet_trend_df.plot(kind='line', figsize=(70, 50), fontsize=26).get_figure().savefig(f'./{self.session_id}/images/trends/trend.svg')
        tweet_trend_df.plot(kind='line', figsize=(70, 50), fontsize=26).get_figure().savefig(f'./{self.session_id}/images/trends/trend.pdf')

        make_archive(base_name=f'./archive/{self.session_id}', format='zip', root_dir=f'./{self.session_id}')
        rmtree(f'./{self.session_id}')
        
    def process_requests(self, search_key, number):
        self.search_key = search_key
        self.tweet_count = number
        self.create_directories()
        self.fetch_tweets()
    
    def tweet_cleaning(self, text):
        regrex_pattern = re.compile(pattern = "["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                            "]+", flags = re.UNICODE)

        clean_tweet = text.decode('utf-8')
        clean_tweet = re.sub(r'^RT[\s]+','', clean_tweet)
        clean_tweet = re.sub(r'https?:\/\/.*[\r\n]*', '', clean_tweet)
        clean_tweet = re.sub(r'#', '', clean_tweet)
        clean_tweet = re.sub(r'@[A-Za-z0–9]+', '', clean_tweet)
        clean_tweet = regrex_pattern.sub(r'', clean_tweet)
        clean_tweet = re.sub('\n',' ', clean_tweet)

        return clean_tweet

    def scaling(self, arr):
        max_value = max(arr)
        j = len(str(max_value))
        
        normalized_like = arr[0] / 10 ** j
        normalized_retweet = arr[1] / 10 ** j

        return normalized_like, normalized_retweet

    def calc_polarity(self, data):
        text = data['text'].encode('utf-8')
        like_count = data['like_count']
        retweet_count = data['retweet_count']

        clean_tweet = self.tweet_cleaning(text)
        like_count_normalized, retweet_count_normalized = self.scaling([like_count, retweet_count])

        polarity = ''
        polarity_score = round(1 + like_count_normalized + retweet_count_normalized, 2)
        analysis = TextBlob(clean_tweet)
        if(analysis.sentiment.polarity == 0):
            self.polarity['neutral'] += polarity_score
            polarity = 'neutral'
        elif(analysis.sentiment.polarity < 0):
            self.polarity['negative'] += polarity_score
            polarity = 'negative'
        elif(analysis.sentiment.polarity > 0):
            self.polarity['positive'] += polarity_score
            polarity = 'positive'

        return polarity, polarity_score
    
    def send_response(self, tweet):
        data = {
            'header': {
                'type': 'GET_TWEETS'
            },
            'body': {
                'tweet': tweet,
                'total_polarity': self.polarity 
            }
        }
        sio.emit('response', data=json.dumps(data), to=self.session_id)
        # sio.sleep(0)
        
    def fetch_tweets(self):
        cursor = Cursor(SentimentAnalysis.tweepy_api.search, q=f'#{self.search_key} -filter:retweets',
                    count=100, tweet_mode='extended', lang='en').items(self.tweet_count)

        df = pd.DataFrame()

        i = 1
        while True:
            print(f'Running... {i}\r', end='')
            try:
                tweet = cursor.next()
                row = {
                    'id': i,
                    'tweet_id': tweet.id,
                    'screen_name': tweet.user.screen_name,
                    'name': tweet.user.name,
                    'tweet_date': str(self.datetime_from_utc_to_local(tweet.created_at)),
                    'location': tweet.user.location,
                    'retweet_count': tweet.retweet_count,
                    'like_count': tweet.favorite_count,
                    'followers_count': tweet.user.followers_count,
                    'following_count': tweet.user.friends_count,
                    'text': tweet.full_text or tweet.text,
                    'embed_url': f'https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}'
                }
                polarity, polarity_score = self.calc_polarity(row)
                row['polarity'], row['polarity_score'] = polarity, polarity_score
                new_rows = pd.DataFrame([row], index=[i])
                df = pd.concat([df, new_rows])
                self.send_response(row)
            except TweepError:
                break
            except RateLimitError:
                break
            except StopIteration:
                break
            i = i + 1
        
        print('\nCompleted')
        self.save_files(df)

sio = socketio.Server(async_mode='eventlet', allow_upgrades=False, ping_interval=1800, ping_terminate=300, cors_allowed_origins =['http://localhost:3000', 'http://localhost:3001'])
app = socketio.WSGIApp(sio)

@sio.event
def connect(sid, environ):
    print(sid, 'CONNECTED')
    data = {
        'header': {
            'type': 'GET_SESSION'
        },
        'body': {
            'session_id': sid
        }
    }
    sio.emit('response', data=json.dumps(data), to=sid)

@sio.event
def disconnect(sid):
    print(sid, 'DISCONNECTED')
    os.remove(f'./archive/{sid}.zip')

@sio.on('request') 
def request(sid, data):
    data = json.loads(data)
    if data['header']['type'] == 'GET':
        key, num = data['body']['search_key'], data['body']['tweet_count']
        senti_analysis = SentimentAnalysis(sid)
        senti_analysis.process_requests(key, num)

Server(eventlet.listen(('localhost', 8000)), app)

