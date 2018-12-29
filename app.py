from flask import Flask, render_template, flash, redirect, url_for, session, logging, request, Markup, jsonify
from flask_mysqldb import MySQL
from passlib.hash import sha256_crypt
from functools import wraps
from wtforms import Form, StringField, TextAreaField, PasswordField, validators, IntegerField, DecimalField, SelectField

app = Flask(__name__)

# config MySQL

app.config['MYSQL_HOST'] = '192.168.0.30'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'x'
app.config['MYSQL_DB'] = 'financy'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# init MySQL

mysql = MySQL(app)

class RegisterForm(Form):
	name = StringField('Navn', [validators.Length(min=1,max=50)])
	username = StringField('Brugernavn', [validators.Length(min=4, max=25)])
	email = StringField('Email', [validators.Length(min=6, max=50)])
	password = PasswordField('Password', [
		validators.DataRequired(),
		validators.EqualTo('confirm', message = 'Adgangskoderne er ikke ens.')
	])
	confirm = PasswordField('Gentag Password')
	companyname = StringField('Firmanavn', [validators.Length(min=3, max=50)])

def is_logged_in(f):
	@wraps(f)
	def wrap(*args, **kwargs):
		if 'logged_in' in session:
			return f(*args, **kwargs)
		else:
			flash('Adgang nægtet. Vær sød at logge ind.', 'danger')
			return redirect(url_for('login'))
	return wrap

@app.route('/logout')
@is_logged_in
def logout():
	session.clear()
	flash('Du er nu logged ud', 'success')
	return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':

		# get form fields
		username = request.form['username']
		password_candidate = request.form['password']

		# Create cursor
		cur = mysql.connection.cursor()

		# Get user by username
		result = cur.execute("SELECT * FROM user WHERE username = %s", [username])

		if result > 0:
			# Get stored hash
			data = cur.fetchone()
			cur.close()
			password = data['password']

			# Compare the Passwords
			if sha256_crypt.verify(password_candidate, password):
				# Passed
				session['name'] = data['name']
				session['logged_in'] = True
				session['username'] = username
				session['uid'] = data['id']

				flash('Du er nu logged ind', 'success')
				return redirect(url_for('office', uid=data['id']))
			else:
				error = 'Ugyldigt login'
				return render_template('login.html', error=error)

		else:
			error = 'Brugernavn ej fundet'
			cur.close()
			return render_template('login.html', error=error)

	return render_template('login.html')

def createNewCompany(userid, companyname):
	cur = mysql.connection.cursor()
	cur.execute('INSERT INTO company(uid, companyname, money) VALUES(%s, %s, %s)', [userid, companyname, "50000"])
	cur.connection.commit()
	cur.close()


@app.route('/register', methods=['GET', 'POST'])
def register():
	form = RegisterForm(request.form)
	if request.method == 'POST' and form.validate():
		name = form.name.data
		email = form.email.data
		username = form.username.data
		password = sha256_crypt.encrypt(str(form.password.data))
		companyname = form.companyname.data

		# create cursor
		cur = mysql.connection.cursor()

		cur.execute("INSERT INTO user(name, email, username, password) VALUES(%s, %s, %s, %s)", (name, email, username, password))

		# commit to db
		mysql.connection.commit()

		cur.execute("SELECT id FROM user WHERE email = %s AND username = %s", [email, username])

		id = cur.fetchone()

		#close con
		cur.close()

		createNewCompany(id['id'], companyname)

		flash('En bruger er blevet registreret og kan nu logge ind', 'success')

		return redirect(url_for('index'))

	return render_template('register.html', form=form)

@app.route('/')
def index():
	return render_template('index.html')

def getTasks(uid):
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM tasks WHERE uid = %s',[uid])
	tasks = {}
	if result > 0:
		tasks = cur.fetchall()

	cur.close()
	return tasks

@app.route('/office/<uid>')
@is_logged_in
def office(uid):
	cur = mysql.connection.cursor()
	cur.execute('SELECT * FROM company WHERE uid=%s', [uid])
	company = cur.fetchone()
	return render_template('office.html', company=company, tasks=getTasks(uid))

@app.route('/createTask')
def createTask():
	cur = mysql.connection.cursor()
	cur.execute("INSERT INTO tasks(uid, title, progress) VALUES(%s,%s,%s)", [session['uid'], "title", "0"])
	cur.connection.commit()
	cur.close()
	return render_template('createtask.html')

if __name__ == '__main__':
	app.secret_key='secret123'
	app.run(debug='true', host='192.168.0.15')
