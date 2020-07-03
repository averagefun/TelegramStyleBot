import json
import os
import boto3
import requests
from PIL import Image
from torchvision.utils import save_image

# import neural style transfer
import NST

# Get vgg19
def model_fn(model_dir):
    return NST.get_model()


# получаем входные картинки
def input_fn(request_body, content_type='application/json'):
    print('loading the input data.')
    if content_type == 'application/json':
        input_data = json.loads(request_body)
        Token, chat_id = input_data['bot_token'], input_data['chat_id']
        t = Telegram(chat_id, Token)
        
        content_image = Image.open(requests.get(input_data['content'], stream=True).raw)
        style_image = Image.open(requests.get(input_data['style'], stream=True).raw)
        max_imgsize = input_data['max_imgsize']
        num_steps = input_data['num_steps']
        assert isinstance(max_imgsize, int)
        
        # обрезаем изображение по контенту
        content_image, style_image = resize_imgs(content_image, style_image, max_imgsize)
        
        return content_image, style_image, num_steps, t
    raise Exception(f'Requested unsupported ContentType in content_type: {content_type}')
    
def resize_imgs(content_image, style_image, max_imgsize):
    content_size = content_image.size
    w,h = content_size
    
    if max(content_size) > max_imgsize:
        if h > w:
            h = max_imgsize
            w = (content_size[0] / content_size[1]) * h
        elif h < w:
            w = max_imgsize
            h = (content_size[1] / content_size[0]) * w
        else:
            h = w = max_imgsize
    
    content_size = (round(h),round(w))
    
    return NST.transform_imgs(content_image, style_image, content_size)

def predict_fn(input_data, model):
    print('Generating prediction based on input parameters.')

    content_img, style_img, num_steps, t = input_data
    # копируем content изображение в input
    input_img = content_img.clone()

    # запускаем style_transfer
    try:
        output = NST.run_style_transfer(model, content_img, style_img, input_img, num_steps = num_steps)
        return output, t
    except Exception as e:
        print(e)
        return None


# выдаём картинку на выход
def output_fn(prediction_output, accept = 'application/json'):
    output, t = prediction_output
    
    # ошибка в style transfer
    if output is None:
        t.finish_query()
        t.send_message("Ошибка при выполнении Style Transfer!\n<i>Пожалуйста, напишите @JwDaKing о этой ошибке.</i>")
        return
    
    filename = 'image.jpg'

    try:
        # сохранение файла
        save_image(output, filename)
    except Exception as e:
        print(e)
        t.finish_query() 
        t.send_message("Внутренняя ошибка при преобразовании pytorch.tensor >> image.jpg. <i>Пожалуйста, напишите @JwDaKing о этой ошибке.</i>")
        return
        
    t.finish_query()                        
        
    # посылаем картинку
    t.send_photo(filename)

    # удаляем файл
    os.remove(filename)
    
    # посылаем сообщение
    t.send_message("<b>Style Transfer успешно завершён!</b>\n<i>Отправьте контент-картинку для нового запроса.</i>",
                  reply_markup=t.markups['content'])
    
    
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