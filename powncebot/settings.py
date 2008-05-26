#JABBER_ID = ''
#JABBER_PASSWORD = ''
#JABBER_RESOURCE = 'bot'
#APPLICATION_KEY = ''

# DATABASE_URI = 'sqlite:///:memory:'

try:
    from local_settings import *
except ImportError:
    pass
