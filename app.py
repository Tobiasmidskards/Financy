from flask import Flask, render_template, flash, redirect, url_for, session, logging, request, Markup, jsonify
from flask_mysqldb import MySQL
from passlib.hash import sha256_crypt
from functools import wraps
from wtforms import Form, StringField, TextAreaField, PasswordField, validators, IntegerField, DecimalField, SelectField
import random
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import math

app = Flask(__name__)

# config MySQL

app.config['MYSQL_HOST'] = '192.168.0.30'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'x'
app.config['MYSQL_DB'] = 'financy'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# init MySQL

mysql = MySQL(app)
scheduler = BackgroundScheduler()


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

class createTaskForm(Form):
	taskname = StringField('Produktnavn', [validators.Length(min=1, max=50)])
	choices = [('audio','Lyd'),('system','System'),('3d','3D')]
	type = SelectField('Type', choices=choices)
	retail = IntegerField('Butikspris')
	choices = [('1','Nem'),('2','Medium'),('3','Svær')]
	niveau = SelectField('Niveau', choices=choices)


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
	return redirect(url_for('index'))

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

def calculateCost(niveau, retail):
	cost = niveau*(retail**4)
	return cost

@app.route('/office/<uid>')
@is_logged_in
def office(uid):
	cur = mysql.connection.cursor()
	cur.execute('SELECT * FROM company WHERE uid=%s', [uid])
	company = cur.fetchone()
	cur.close()
	return render_template('office.html', company=company, tasks=getTasks(uid))

def updateTasks():
	with app.app_context():
		cur = mysql.connection.cursor()
		result = cur.execute('SELECT * FROM tasks')
		if result > 0:
			tasks = cur.fetchall()
			for task in tasks:
				progress = int(task['progress'])
				type = task['type']
				niveau = int(task['niveau'])
				potential = int(task['potential'])
				reach = int(task['reach'])
				retail = int(task['retail'])
				status = int(task['status'])
				quality = int(task['quality'])

				if progress==0:
					progress = 2

				if (progress < 101 and progress > 0 and status == 0):
					progress += potential*math.sqrt(progress)/niveau/24

					if (progress > 99):
						progress = 100

					#value = niveau*(potential**2)*progress/(retail**3)
					cur.execute('UPDATE tasks SET progress = %s WHERE id = %s',[str(progress) ,task['id']])
					cur.connection.commit()
				elif (progress < 101 and progress > 0 and status == 1):
					progress += potential/niveau/12

					if (progress > 99):
						progress = 100

					reach = niveau*(potential**3)*progress/(retail**2)*quality/100
					value = reach*retail*quality/100
					cur.execute('UPDATE tasks SET progress = %s, reach = %s, value = %s WHERE id = %s',[str(progress), str(reach), str(value) ,task['id']])
					cur.connection.commit()
				else:
					cur.execute('UPDATE tasks SET progress = %s WHERE id = %s',["1" ,task['id']])
					cur.connection.commit()
		cur.close()

def companyMoney(amount, method):
	cur = mysql.connection.cursor()
	cur.execute('SELECT money FROM company WHERE uid = %s', [session['uid']])
	money = cur.fetchone()
	if method:
		updatedMoney = money['money'] + amount
	else:
		updatedMoney = money['money'] - amount
	cur.execute('UPDATE company SET money = %s WHERE uid = %s', [updatedMoney, session['uid']])
	cur.connection.commit()
	cur.close()

@app.route('/promoteTask/<taskid>')
def promoteTask(taskid):
	cur = mysql.connection.cursor()
	cur.execute('SELECT progress FROM tasks WHERE id = %s', [taskid])
	quality = cur.fetchone()
	cur.execute('UPDATE tasks SET status = %s, progress = %s, quality = %s WHERE id = %s', ["1", "0", str(quality['progress']), taskid])
	cur.connection.commit()
	cur.close()
	return redirect(url_for('office', uid=session['uid']))

@app.route('/sellTask/<taskid>')
def sellTask(taskid):
	cur = mysql.connection.cursor()
	cur.execute('SELECT value FROM tasks WHERE id = %s', [taskid])
	value = cur.fetchone()
	cur.execute('SELECT money FROM company WHERE uid = %s', [session['uid']])
	money = cur.fetchone()
	companyMoney(value['value'],True)
	cur.execute('UPDATE tasks SET sold = %s WHERE id = %s', ["1", taskid])
	cur.connection.commit()
	cur.close()
	flash('Du har nu solgt dit produkt', 'success')
	return redirect(url_for('office', uid=session['uid']))

@app.route('/createTask', methods=['GET', 'POST'])
def createTask():
	form = createTaskForm(request.form)

	if request.method == 'POST' and form.validate():
		taskname = form.taskname.data
		type = form.type.data
		retail = form.retail.data
		niveau = form.niveau.data
		potential = random.randint(20,101)

		cur = mysql.connection.cursor()
		cur.execute("INSERT INTO tasks(uid, title, progress, value, type, retail, niveau, potential, status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
					[session['uid'], taskname, "0", "0", type, str(retail), str(niveau), potential, "0"])

		cur.connection.commit()
		cur.close()
		flash('Din opgave er sat i værk!', 'success')
		return redirect(url_for('office', uid=session['uid']))


	return render_template('createtask.html', form=form)


scheduler.add_job(func=updateTasks, trigger="interval", hours=1)
scheduler.start()

if __name__ == '__main__':
	app.secret_key='secret123'
	app.run( host='192.168.0.15')

atexit.register(lambda: scheduler.shutdown())
