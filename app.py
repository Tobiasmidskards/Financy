from flask import Flask, render_template, flash, redirect, url_for, session, logging, request, Markup, jsonify
from flask_mysqldb import MySQL

app = Flask(__name__)

# config MySQL

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '12345678'
app.config['MYSQL_DB'] = 'financy'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# init MySQL

mysql = MySQL(app)

@app.route('/')
def index():
	return render_template('index.html')

if __name__ == '__main__':
	app.secret_key='secret123'
	app.run(debug='true', host='192.168.0.15')
