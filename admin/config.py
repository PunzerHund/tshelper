import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me')
    BASE_MENTORS_DIR = '/opt/mentors'
