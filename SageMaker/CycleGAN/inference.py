import json
import os
import requests
import boto3


# Fake function for SageMaker template
def model_fn(model_dir):
    # go to code directory
    os.chdir('./code')
    model = 'empty_model'
    return model


def input_fn(request_body, content_type='application/json'):
    input_data = json.loads(request_body)
    
    Token, chat_id = input_data['bot_token'], input_data['chat_id']
    t = Telegram(chat_id, Token)
    model_name = input_data['style']

    # download content from telegram
    content = input_data['content']
    format_ = content.split('.')[-1]
    
    with open (f'mydataset/image.{format_}', 'wb') as f:
        r = requests.get(content)
        f.write(r.content)

    return model_name, t


def predict_fn(input_data, model):
    model_name, t = input_data
    os.system(f"python test.py --name {model_name}")
    return t

def output_fn(prediction_output, accept = 'application/json'):  
    t = prediction_output
    
    t.finish_query()
    
    # посылаем картинку
    t.send_photo('results/image_fake.jpg')
    t.send_message("<b>CycleGAN успешно завершён.</b>\n<i>Отправьте файл для нового запроса.</i>", reply_markup=t.markups['content'])

    
# Telegram Class
class Telegram:
    def __init__(self, chat_id, Token):
        self.chat_id = chat_id
        self.URL = "https://api.telegram.org/bot{}/".format(Token)
        self.markups={'content': {'keyboard': [['Отправьте контент-картинку боту!📷']], 'resize_keyboard': True}}
        
    def send_photo(self, filename):
        url = self.URL + 'sendPhoto'
        with open(filename, 'rb') as file:
            files = {'photo': file}
            data = {'chat_id': self.chat_id, 'title': 'StylePhoto'}
            requests.post(url, files=files, data=data)

    def send_message(self, text, reply_markup = None):
        url = self.URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML".format(self.chat_id, text)
        if reply_markup:
            url+=f"&reply_markup={json.dumps(reply_markup)}"
        requests.get(url)

    def delete_message(self, message_id):
        url = self.URL + "deleteMessage?chat_id={}&message_id={}".format(self.chat_id, message_id)
        requests.get(url)
        
    def finish_query(self):
        # подключение к DynamoDB
        db = DynamoDB('ImageIdTable')

        # удаляем ждущий стикер
        message_id = db.get_item(self.chat_id)
        if message_id:
            self.delete_message(message_id[4:])

        # удаляем запрос пользователя в таблице
        db.delete_item(self.chat_id)
    
    
# DynamoDB table
class DynamoDB:
    def __init__(self, name):
        dynamodb = boto3.resource('dynamodb')
        self.table = dynamodb.Table(name)

    def get_item(self, user_id):
        response = self.table.get_item(Key={'user_id': user_id})
        if 'Item' in response.keys():
            return response['Item']['file_id']
        
    def delete_item(self, user_id):
        self.table.delete_item(
            Key={
                'user_id': user_id,
            }
        )
    


