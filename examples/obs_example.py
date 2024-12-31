import obsws_python
from poolguy.twitch import TwitchBot, Alert, ColorLogger

logger = ColorLogger(__name__)

class OBSController:
    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self.cfg = {"host": self.host, "port": self.port, "password": self.password}
        self.reqws = obsws_python.ReqClient(**self.cfg)
        self.eventws = obsws_python.EventClient(**self.cfg)

    def showSource(self, source_name):
        self.reqws.set_input_settings(
                    input_name=source_name,
                    input_settings={"visible": True},
                    overlay=True
                )

    def hideSource(self, source_name):
        self.reqws.set_input_settings(
                    input_name=source_name,
                    input_settings={"visible": False},
                    overlay=True
                )

class MyBot(TwitchBot):
    def __init__(self, obs_creds, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.obsws = OBSController(**obs_creds)
        self.obsws.eventws.callback.register(self.on_media_input_playback_ended)
        
    def on_media_input_playback_ended(self, data):
        """ Hides a media source when it is finished playing """
        try:
            self.obsws.hideSource(data.input_name)
        except Exception as e:
            print(f"Error hiding media source: {data.input_name}\n {e}")


class ChannelChatMessageAlert(Alert):
    """channel.chat.message"""
    async def process(self):
        logger.debug(f'{self.data}')
        logger.info(f'[Chat] {self.data['chatter_user_name']}: {self.data['message']['text']}', 'purple')


if __name__ == '__main__':
    import logging
    logging.basicConfig(
        format="%(asctime)s-%(levelname)s-[%(name)s] %(message)s",
        datefmt="%I:%M:%S%p",
        level=logging.DEBUG
    )

    bot = MyBot(
            # my custom args for my personalized bot (obs websocket connection)
            obs_creds={
                "host": "localhost",
                "port": "6969",
                "password": "password123"
            }, 
            # twitch api creds
            # redirect_uri route will automagicly be setup so a user token can be acquired
            # example: 
            #   "http://localhost:4200/deez" -> 
            #       '/deez' route will be set to a Quart webserver running on 'localhost:4200'
            creds={
                "client_id": "clientid123supersecret",
                "client_secret": "clientsecret123verysecret",
                "redirect_uri": "http://localhost:4200/deez",
                "scopes": [
                    "user:read:email",
                    "user:read:emotes",
                    "user:read:chat",
                    "chat:read",
                    "chat:edit",
                ]
            }, 
            # list of channels to subscribe the websocket to
            # you will want a subclass of 'Alert' named the same
            # as each Event channel you are subscribing to
            # but with '.' removed, CapitalCamelCase and 'Alert' 
            # appended to the end 
            # example: 'channel.chat.message' -> 'ChannelChatMessageAlert'
            channels=["channel.chat.message"], 
            # list of channels NOT to add to the queue
            # these channels will be processed on a seperate 'asyncio.create_task'
            # rather than waiting in the queue
            queue_skip=["channel.chat.message"], 
            # alert queue storage type
            # possible = 'json', 'sqlite3', 'mongodb'
            storage_type='json')
    bot.run()