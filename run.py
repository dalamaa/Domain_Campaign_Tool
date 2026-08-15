import sys
import flask 
print("PYTHON:", sys.executable)
print("VERSION:", sys.version)

import psycopg2
print("PSYCOPG2:", psycopg2.__version__)

import os
with open("requirements.txt", "r") as f:
    print("REQUIREMENTS:", f.read())

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)

