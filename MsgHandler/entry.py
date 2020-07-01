import json
import boto3
import requests

### Управление ботом

# включение/выключение бота
bot_active = True

# максимальный объём присылаемой фотографии в телеграм (Кб)
maxsize = 500

# клавиатура установленных стилей
style_markup = json.dumps({'keyboard': [['Лето >> Зима'], ['Зима >> Лето']], 'resize_keyboard': True})

# получаем токен бота из файла
with open('cred.txt') as file:
    Token = file.readline()
URL = "https://api.telegram.org/bot{}/".format(Token)

def lambda_handler(event, context):
    # обрабатываем любые исключения
    try:
        event = json.loads(event['body'])
        print(event)
        msg_handler(event)
    except Exception as e:
        print(f'ERROR:{e} || EVENT:{event}')

    # в любом случае возвращаем телеграму код 200
    return {'statusCode': 200}


def msg_handler(event):
    # проверяем, что это сообщение
    try:
        msg = event['message']
    except KeyError:
        return
    # инициализация пользователя
    user_id = msg['chat']['id']

    # если бот не активены
    if not bot_active:
        send_message(user_id, "Чтобы активировать бота, напишите @JwDaKing!")
        return

    # подключение к DynamoDB
    db = DynamoDB('ImageIdTable')

    if 'photo' in msg.keys():
        photo_handler(user_id, msg['photo'], db)
    elif 'text' in msg.keys():
        styles = {'Лето >> Зима': 'summer2winter_yosemite',
                  'Зима >> Лето': 'winter2summer_yosemite'}

        text = msg['text']
        if text[0] == '/':
            # это команда
            commands_handler(user_id, msg['text'], db)
        else:
            # проверяем наличие в таблице этого пользователя
            content_id = db.get_item(user_id)
            if not content_id or content_id[:4] != 'wait':
                if text in styles:
                    # пользователь выбрал установленный стиль
                    send_message(user_id, "<b>Ок!</b>")
                    message_id = send_sticker(user_id, 'loading')
                    db.update_item(user_id, message_id)

                    style = styles[text]
                    content = get_file(content_id)
                    # invoke_SM('CycleGAN', user_id, content, style)
                else:
                    send_message(user_id, "Отправь мне <b>картинку</b> или выбери значение на клавиатуре!",
                                          "reply_markup", style_markup)
            else:
                send_message(user_id,
                             "<b>Пожалуйста, дождитесь ответа бота!</b>\n<i>В случае ожидания более 2 минут, отправьте <b>/cancel</b>.</i>")

    else:
        send_message(user_id, "<b>Нераспознанный файл!</b>\n<i>Отправляйте картинку как картинку, а не как файл!</i>")


def photo_handler(user_id, photo, db):
    # проверяем наличие в таблице этого пользователя
    content_id = db.get_item(user_id)
    if content_id:
        if content_id[:4] == 'wait':
            # пользователь отправил новую фотографию, когда бот ещё не обработал старую
            send_message(user_id,
                         "Пожалуйста, дождитесь ответа бота!\nВ случае ожидания более 2 минут, отправьте <b>/cancel</b>.")
        else:
            # пользователь посылает 2 картинку (style image)
            style_id = check_photo(user_id, photo)
            if not style_id:
                return
            send_message(user_id, "<b>Стиль-картинка принята!</b>")
            message_id = send_sticker(user_id, 'loading')
            db.update_item(user_id, message_id)
            content = get_file(content_id)
            style = get_file(style_id)
            invoke_SM('NST', user_id, content, style)
    else:
        # пользователь посылает 1 картинку (content image)
        content_id = check_photo(user_id, photo)
        if not content_id:
            return
        db.put_item(user_id, content_id)
        send_message(user_id, "<b>Контент-картинка принята!</b>\nТеперь отправь стиль-картинку или выбери установленный стиль!",
                              "reply_markup", style_markup)

# проверка на размер фотографии
def check_photo(user_id, photos):
    photos.reverse()
    for photo in photos:
        if photo['file_size'] < maxsize * 1000:
            return photo['file_id']

    send_message(user_id, "Пожалуйста, отправьте фотографию меньшего размера!")


# обрабатываем команды
def commands_handler(user_id, command, db):
    commands = ['/start', '/help', '/cancel']
    if command not in commands:
        send_message(user_id, "<b>Такой команды не существует!</b>")
        return
    if command == '/start':
        db.delete_item(user_id)
        send_sticker(user_id, 'start')
        send_message(user_id,
                     "<b>Привет!</b>\nЧтобы начать, отправь мне картинку!")
    elif command == '/help':
        help_text = """Simple help text"""
        send_message(user_id, help_text)
    elif command == '/cancel':
        db.delete_item(user_id)
        send_message(user_id, "<b>Запрос отменён!</b>\n<i>Отправьте контент-картинку снова!</i>")


def invoke_SM(net_type, chat_id, content, style):

    if net_type == 'NST':
        name = 'NeuralStyleTransferPoint'
        body = {'content': content, 'style': style,
                'max_imgsize': 1024, 'bot_token': Token,
                'chat_id': chat_id, 'num_steps': 200}

    elif net_type == 'CycleGAN':
        name = 'CycleGANPoint'
        body = {'content': content, 'style': style,
                'chat_id': chat_id}

    else:
        raise NameError("Network not found")

    client = boto3.client('sagemaker-runtime')
    response = client.invoke_endpoint(
    EndpointName=name,
    Body=json.dumps(body),
    ContentType='application/json',
    )
    return response

class DynamoDB:
    def __init__(self, name):
        dynamodb = boto3.resource('dynamodb')
        self.table = dynamodb.Table(name)

    def get_item(self, user_id):
        response = self.table.get_item(Key={'user_id': user_id})
        if 'Item' in response.keys():
            return response['Item']['file_id']

    def put_item(self, user_id, file_id):
        self.table.put_item(
            Item={
                'user_id': user_id,
                'file_id': file_id,
            }
        )

    def update_item(self, user_id, message_id):
        self.table.update_item(
            Key={
                'user_id': user_id
            },
            UpdateExpression="set file_id=:w",
            ExpressionAttributeValues={
                ':w': f'wait{message_id}'
            })

    def delete_item(self, user_id):
        self.table.delete_item(
            Key={
                'user_id': user_id,
            }
        )


# Telegram methods
def send_message(chat_id, text, *args):  # Ф-ия отсылки сообщения/ *args: [0] - parameter_name, [1] - value
    if len(args) == 0:
        url = URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML".format(chat_id, text)
    elif len(args) == 2:
        url = URL + "sendMessage?chat_id={}&text={}&{}={}&parse_mode=HTML".format(chat_id, text, args[0], args[1])
    r = requests.get(url).json()
    return r


def delete_message(chat_id, message_id):
    url = URL + "deleteMessage?chat_id={}&message_id={}".format(chat_id, message_id)
    requests.get(url)


def send_sticker(chat_id, sticker):
        stickers = {
            'start': 'CAACAgIAAxkBAAMzXrVojwLgjpqLL8gJ4HbWwzLAO2oAAgEBAAJWnb0KIr6fDrjC5jQZBA',
            'loading': 'CAACAgIAAxkBAAN_Xre2LtYeBDA-3_ewh5kMueCsRWsAAgIBAAJWnb0KTuJsgctA5P8ZBA'
        }
        url = URL + "sendSticker?chat_id={}&sticker={}&parse_mode=HTML".format(chat_id, stickers[sticker])
        r = requests.get(url).json()
        return r['result']['message_id']


def get_file(file_id):
    url = URL + "getFile?file_id={}".format(file_id)
    r = requests.get(url)
    file = json.loads(r.content)
    assert file['result']['file_size'] <= maxsize * 1000
    file_path = file['result']['file_path']
    url = 'https://api.telegram.org/file/bot{}/{}'.format(Token, file_path)
    return url
