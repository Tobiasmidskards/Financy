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

class newEmployeeForm(Form):
	firstname = StringField('Navn', [validators.Length(min=2, max=10)])
	lastname = StringField('Efternavn', [validators.Length(min=2, max=10)])

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
	cur.execute('INSERT INTO company(uid, companyname) VALUES(%s, %s)', [userid, companyname])
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

@app.route('/hire/<employeeid>')
def hire(employeeid):
	cur = mysql.connection.cursor()
	cur.execute('UPDATE employee SET companyid = %s WHERE id = %s',[session['uid'] , employeeid])
	cur.connection.commit()
	cur.close()
	return redirect(url_for('employee', employeeid=employeeid))


@app.route('/createEmployee', methods=['GET', 'POST'])
def createEmployee():
	form = newEmployeeForm(request.form)

	if request.method == 'POST' and form.validate():
		firstname = form.firstname.data
		lastname = form.lastname.data
		cur = mysql.connection.cursor()

		potential = str(random.randint(10,101))

		cur.execute('INSERT INTO employee(firstname, lastname, potential, discoveredby) VALUES(%s, %s, %s, %s)', [firstname, lastname, potential, session['uid']])
		cur.connection.commit()
		cur.execute('SELECT LAST_INSERT_ID() as id')
		id = cur.fetchone()
		cur.close()
		return redirect(url_for('employee', employeeid=id['id']))

	return render_template('createEmployee.html', form=form)

@app.route('/employees')
def employees():
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM employee WHERE companyid = %s', ["-1"])
	if result > 0:
		employees = cur.fetchall()
		for employee in employees:
			employee['sum'] = getStatsSum(employee)
		cur.close()
		return render_template('employees.html', employees=employees)
	cur.close()
	return render_template('employees.html')

@app.route('/employee/<employeeid>')
def employee(employeeid):
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM employee WHERE id = %s',[employeeid])
	if result > 0:
		employee = cur.fetchone()

		employee['sum'] = getStatsSum(employee)

		companyname = {}
		if employee['companyid'] != -1:
			cur.execute("SELECT companyname FROM company WHERE uid = %s", [employee['companyid']])
			companyname = cur.fetchone()
		else:
			companyname['companyname'] = "Arbejdsløs"

		cur.execute("SELECT companyname FROM company WHERE uid = %s", [employee['discoveredby']])
		discoveredby = cur.fetchone()

		companyname['discoveredby'] = discoveredby['companyname']

		cur.close()
		return render_template('employee.html', employee=employee, companyname=companyname)
	cur.close()

@app.route('/office/<uid>')
@is_logged_in
def office(uid):
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM company WHERE uid=%s', [uid])
	if result > 0:
		company = cur.fetchone()
		cur.close()
		if company['uid'] == session['uid']:
			cur.close()
			return render_template('office.html', company=company, tasks=getTasks(uid), stab=getStab(uid))
	cur.close()
	return redirect(url_for('index'))

def getStatsSum(employee):
	sum = int(employee['audio']) + int(employee['system']) + int(employee['graphic'])
	sum += int(employee['frontend']) + int(employee['backend']) + int(employee['marketing'])
	return str(sum)

def getStab(companyid):
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM employee WHERE companyid = %s',[companyid])
	if result > 0:
		employees = cur.fetchall()
		for employee in employees:
			employee['sum'] = getStatsSum(employee)
		cur.close()
		return employees
	cur.close()
	return {}

def getStabSum(companyid):
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM employee WHERE companyid = %s',[companyid])
	sum = 0
	if result > 0:
		employees = cur.fetchall()
		for employee in employees:
			sum += int(getStatsSum(employee))
	cur.close()
	return sum


def companyMoney(amount, method, uid = "default"):
	if uid is "default":
		uid = session['uid']

	cur = mysql.connection.cursor()
	cur.execute('SELECT money FROM company WHERE uid = %s', [uid])
	money = cur.fetchone()

	if method:
		updatedMoney = money['money'] + amount
	else:
		updatedMoney = money['money'] - amount

	if updatedMoney < 0:
		flash('Du har ikke råd!', 'danger')
		cur.close()
		return False

	cur.execute('UPDATE company SET money = %s WHERE uid = %s', [updatedMoney, uid])
	cur.connection.commit()
	cur.close()
	return True

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

		if companyMoney(100000,False):
			cur = mysql.connection.cursor()
			cur.execute("INSERT INTO tasks(uid, title, progress, value, type, retail, niveau, potential, status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
						[session['uid'], taskname, "0", "0", type, str(retail), str(niveau), potential, "0"])

			cur.connection.commit()
			cur.close()

			flash('Din opgave er sat i værk!', 'success')
			return redirect(url_for('office', uid=session['uid']))


	return render_template('createtask.html', form=form)

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
				userid = int(task['uid'])

				if progress==0:
					progress = 2

				if (progress < 101 and progress > 0 and status == 0):

					stabforce = getStabSum(userid)
					if stabforce == 0:
						stabforce = 10

					delta = (potential*math.sqrt(stabforce*50)/niveau/24/12)+1
					print(delta)
					progress += delta

					if (progress > 99):
						progress = 100

					#value = niveau*(potential**2)*progress/(retail**3)
					cur.execute('UPDATE tasks SET progress = %s WHERE id = %s',[str(progress) ,task['id']])
					cur.connection.commit()
				elif (progress < 101 and progress > 0 and status == 1):
					stabforce = getStabSum(userid)
					if stabforce == 0:
						stabforce = 10
					delta = (potential*math.sqrt(stabforce*50)/niveau/24/12)+1
					progress += delta

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

def paySalary():
	with app.app_context():
		cur = mysql.connection.cursor()
		cur.execute("SELECT companyid, salary FROM employee")
		employees = cur.fetchall()

		for employee in employees:
			if employee['companyid'] != -1:
				cur.execute("SELECT money FROM company WHERE uid = %s", [employee['companyid']])
				money = cur.fetchone()
				money = money['money'] - employee['salary']
				cur.execute("UPDATE company SET money = %s WHERE uid = %s", [money, employee['companyid']])
				cur.connection.commit()
		cur.close()


def newDay():
	with app.app_context():
		cur = mysql.connection.cursor()
		result = cur.execute('SELECT id, year, day FROM employee')
		if result > 0:
			employees = cur.fetchall()
			for employee in employees:
				year = int(employee['year'])
				day = int(employee['day'])
				if day > 29:
					day = 0
					year = year + 1
				else:
					day = day + 1
				cur.execute("UPDATE employee SET year = %s, day = %s WHERE id = %s", [str(year), str(day), employee['id']])
				cur.connection.commit()
		cur.close()

#def test():
	#paySalary()
	#newDay()
	#updateTasks()

scheduler.add_job(paySalary, 'cron', hour=0)
scheduler.add_job(newDay, 'cron', hour=0)
scheduler.add_job(updateTasks, 'cron', hour='0-23', minute='0,30')
scheduler.start()


if __name__ == '__main__':
	app.secret_key='secret123'
	app.run(host='192.168.0.15', threaded=True)

atexit.register(lambda: scheduler.shutdown())
