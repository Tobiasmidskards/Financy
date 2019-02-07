from flask import Flask, render_template, flash, redirect, url_for, session, logging, request, Markup, jsonify
from flask_mysqldb import MySQL
from passlib.hash import sha256_crypt
from functools import wraps
from wtforms import Form, StringField, TextAreaField, PasswordField, validators, IntegerField, DecimalField, SelectField
import random
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import math
from werkzeug.utils import secure_filename
import os
from flask import send_from_directory
import smtplib
from forms import *


UPLOAD_FOLDER = '/home/pi/Financy/uploads'
ALLOWED_EXTENSIONS = set(['png'])


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# config MySQL

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'tobias'
app.config['MYSQL_PASSWORD'] = 'xxx'
app.config['MYSQL_DB'] = 'financy'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# init MySQL

mysql = MySQL(app)
scheduler = BackgroundScheduler()


def allowed_file(filename):
	return '.' in filename and \
		   filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
	if request.method == 'POST':
		# check if the post request has the file part
		if 'file' not in request.files:
			flash('No file part')
			return redirect(request.url)
		file = request.files['file']
		# if user does not select file, browser also
		# submit an empty part without filename
		if file.filename == '':
			flash('No selected file')
			return redirect(request.url)
		if file and allowed_file(file.filename):
			filename = secure_filename(file.filename)
			filename = str(session['uid']) + '.png'
			file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
			flash('Du har nu uploaded et nyt logo.', 'success')
			return redirect(url_for('office', uid = session['uid']))

	return render_template('upload.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
	return send_from_directory(app.config['UPLOAD_FOLDER'],
							   filename)

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

@app.route('/market')
def market():
	printUser()
	company = {}
	cur = mysql.connection.cursor()
	cur.execute("SELECT * FROM company")
	companies = cur.fetchall()
	for company in companies:
		cur.execute("SELECT name FROM user WHERE id = %s", [company['uid']])
		company['ceo'] = cur.fetchone()['name']
		cur.execute("SELECT count(*) as sum FROM tasks WHERE uid = %s", [company['uid']])
		company['productsum'] = cur.fetchone()['sum']
		company['valuation'] = int(getValuation(company['uid']))
	cur.close()
	return render_template('market.html', companies=companies)

@app.route('/hire/<employeeid>')
def hire(employeeid):
	cur = mysql.connection.cursor()
	cur.execute("SELECT count(*) as amount FROM employee WHERE companyid = %s", [session['uid']])
	amount = cur.fetchone()['amount']
	cur.execute("SELECT office FROM company WHERE uid = %s", [session['uid']])
	office = cur.fetchone()['office']

	if amount <= (office * 3):
		cur.execute('UPDATE employee SET companyid = %s WHERE id = %s',[session['uid'] , employeeid])
		cur.connection.commit()
		flash('Du har nu ansat medarbejeren.', 'success')
	else:
		flash('Du kan ikke ansætte flere. Opgradér dit Kontorniveau.', 'danger')
	cur.close()
	return redirect(url_for('employee', employeeid=employeeid))

@app.route('/fire/<employeeid>')
def fire(employeeid):
	cur = mysql.connection.cursor()

	cur.execute('UPDATE employee SET companyid = %s WHERE id = %s',["-1" , employeeid])
	cur.connection.commit()
	flash('Du har nu fyret medarbejeren.', 'success')
	cur.close()
	return redirect(url_for('employee', employeeid=employeeid))

def createEmployees():
	cur = mysql.connection.cursor()

	first = ["Tobias", "Joakim", "Morten", "Frederik", "Lærke", "Mathilde", "Mads", "Villum", "Svend", "Ebbe", "Aske", "Jens", "Laust", "Søren", "William", "Oliver", "Victor", "Elias", "Valdemar", "Magnus", "Felix", "Nohr", "Alexander", "Liam", "Sebastian"]
	last = ["Sørensen", "Madsen", "Ahmad", "Andersen", "Bach", "Bak", "Bruun", "Damgaard", "Eriksen", "Frederiksen", "Gade", "Frost", "Holm", "Friis", "Hoffman", "Iversen"]

	for i in range(0,50):
		potential = str(random.randint(10,101))

		random1 = random.randint(0,len(first)-1)
		random2 = random.randint(0,len(last)-1)

		frontend = str(random.randint(3,9))
		marketing = str(random.randint(3,9))
		backend = str(random.randint(3,9))
		audio = str(random.randint(3,9))
		graphic = str(random.randint(3,9))
		system = str(random.randint(3,9))
		year = str(random.randint(15,31))

		firstname = first[random1]
		lastname = last[random2]
		discoveredby = "13"

		print(firstname, " ", lastname)

		cur.execute('INSERT INTO employee(firstname, lastname, potential, discoveredby, frontend, marketing, backend, audio, graphic, system, year) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', [firstname, lastname, potential, session['uid'], frontend, backend, marketing, audio, graphic, system, year])
		cur.connection.commit()

	cur.close()

@app.route('/createEmployee', methods=['GET', 'POST'])
def createEmployee():
	form = newEmployeeForm(request.form)

	if (getCompanyType() < 3):
		flash('Du skal opgradere din virksomhedstype for at hente nyuddannede.', 'danger')
		return redirect(url_for('office', uid=session['uid']))

	if request.method == 'POST' and form.validate():
		firstname = form.firstname.data
		lastname = form.lastname.data
		cur = mysql.connection.cursor()

		potential = str(random.randint(10,101))

		frontend = str(random.randint(3,9))
		marketing = str(random.randint(3,9))
		backend = str(random.randint(3,9))
		audio = str(random.randint(3,9))
		graphic = str(random.randint(3,9))
		system = str(random.randint(3,9))

		cur.execute('INSERT INTO employee(firstname, lastname, potential, discoveredby, frontend, marketing, backend, audio, graphic, system) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', [firstname, lastname, potential, session['uid'], frontend, backend, marketing, audio, graphic, system])

		cur.connection.commit()
		cur.execute('SELECT LAST_INSERT_ID() as id')
		id = cur.fetchone()
		cur.close()
		return redirect(url_for('employee', employeeid=id['id']))

	return render_template('createEmployee.html', form=form)

@app.route('/employees')
def employees():
	printUser()
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM employee WHERE companyid = %s', ["-1"])
	if result > 0:
		employees = cur.fetchall()
		for employee in employees:
			employee['salary'] = "{:,}".format(int(employee['salary']))
			employee['sum'] = getStatsSum(employee)
		cur.close()
		return render_template('employees.html', employees=employees)
	cur.close()
	return render_template('employees.html')

@app.route('/employee/<employeeid>/settings', methods=['GET', 'POST'])
def employeeSettings(employeeid):

	if (getCompanyType() < 3):
		flash('Du skal opgradere din virksomhedstype for at låse denne mulighed op.', 'danger')
		return redirect(url_for('employee', employeeid=employeeid))

	form = jobTitleForm(request.form)

	cur = mysql.connection.cursor()
	cur.execute("SELECT * FROM employee WHERE id=%s", [employeeid])
	employee = cur.fetchone()

	form.jobtitle.data = employee['Jobtitle']

	if request.method == 'POST' and form.validate():
		jobtitle = request.form['jobtitle']

		cur.execute("UPDATE employee SET Jobtitle = %s WHERE id = %s", [jobtitle, employeeid])
		cur.connection.commit()
		cur.close()
		msg = "{} har nu skiftet titel.".format(employee['firstname'])
		flash(msg, 'success')
		return redirect(url_for('employee', employeeid=employeeid))

	cur.close()
	return render_template('employeesettings.html', form=form, employee=employee)

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

		result = cur.execute("SELECT * FROM (SELECT xp, date FROM concentrations WHERE employeeid=%s ORDER BY date DESC LIMIT 365) sub ORDER BY date ASC", [employee['id']])

		concentrations = {}

		if result > 0:
			concentrations = cur.fetchall()
			for concentration in concentrations:
				concentration['date'] = concentration['date'].date()

		cur.close()
		return render_template('employee.html', employee=employee, companyname=companyname, concentrations=concentrations, companytype=getCompanyType())
	cur.close()

@app.route('/globalmsgOK')
def globalmsgOK():
	cur = mysql.connection.cursor()
	cur.execute("UPDATE company SET globalmsg = %s WHERE uid = %s", [0, session['uid']])
	cur.connection.commit()
	cur.close()
	return redirect(url_for('office', uid=session['uid']))

def getTeamsizes(companyid):
	teamsizes = {}
	cur = mysql.connection.cursor()
	cur.execute("SELECT COUNT(*) as total FROM employee WHERE companyid = %s", [companyid])
	teamsizes.update(cur.fetchone())
	cur.execute("SELECT COUNT(*) as dev FROM employee WHERE companyid = %s and Jobtitle = %s", [companyid, "dev"])
	teamsizes.update(cur.fetchone())
	cur.execute("SELECT COUNT(*) as mark FROM employee WHERE companyid = %s and Jobtitle = %s", [companyid, "mark"])
	teamsizes.update(cur.fetchone())
	cur.execute("SELECT COUNT(*) as sale FROM employee WHERE companyid = %s and Jobtitle = %s", [companyid, "sale"])
	teamsizes.update(cur.fetchone())
	cur.close()
	return teamsizes

@app.route('/office/<uid>')
@is_logged_in
def office(uid):
	printUser()
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM company WHERE uid=%s', [uid])
	if result > 0:
		company = cur.fetchone()

		company['money'] = "{:,}".format(company['money'])

		# Global message
		if company['globalmsg'] == 1 and session['uid'] == int(uid):
			return render_template('globalmsg.html')

		cur.execute("SELECT name FROM user WHERE id = %s", [company['uid']])
		company['ceo'] = cur.fetchone()['name']

		teamsizes = getTeamsizes(company['uid'])

		copiesmsg, fansmsg = False, False
		tasks = getTasks(uid)

		for task in tasks:
			task['value'] = int(task['value'])
			task['potential'] = int(task['potential'])

			hypemsg = False
			if task['status'] == 2:
				if task['copies'] == 0:
					copiesmsg = True
				if (task['quality'] < 50 or task['potential'] < 50) and company['fans'] < 200:
					fansmsg = True
				if task['hype'] < 0.1:
					hypemsg = True

				if hypemsg and session['uid'] == int(uid):
					msg = "Kunderne er ved at miste interessen for {}. Overvej at nedlæg produktet.".format(task['title'])
					flash(msg, 'danger')

			if task['status'] == 0 and task['quality'] < 70 and session['uid'] == int(uid) and task['progress'] > 90:
				msg = "Dit produkt {} har en lav kvalitet. Jo bedre ansatte du har, jo mere øges kvaliteten.".format(task['title'])
				flash(msg, 'danger')

			if task['status'] == 10 and task['progress'] > 105 and session['uid'] == int(uid):
				msg = "{} er nu klar til at blive færdiggjordt. Sælg produktet inden det falder i værdi.".format(task['title'])
				flash(msg, 'danger')

		if session['uid'] == int(uid):
			if copiesmsg:
				flash('Du har produkter som er udsolgt. Det bryder dine fans sig ikke om. Producér nogle flere eller nedlæg produkterne.', 'danger')
			if fansmsg:
				flash('Du sælger produkter med dårlig kvalitet eller potentiale. Det bryder dine fans sig ikke om. Nedlæg fiskoerne.', 'danger')

		logo = os.path.join('/uploads', str(company['uid']) + '.png')
		if not (os.path.isfile(logo[1:])):
			logo = 'http://argot.fr/wp-content/plugins/uix-shortcodes/admin/uixscform/images/no-logo.png'

		return render_template('office.html', company=company, tasks=tasks, stab=getStab(uid), logo=logo, teamsizes=teamsizes)
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

def getStabSum(companyid, department):
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM employee WHERE companyid = %s',[companyid])
	sum = 20
	if result > 0:
		employees = cur.fetchall()
		for employee in employees:
			if employee['Jobtitle'] == department:
				sum += int(getStatsSum(employee))
	cur.close()
	print("cid:{} - dep:{} - sum:{}".format(companyid, department, sum))
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

	if updatedMoney < 0 and not method:
		flash('Du har ikke råd!', 'danger')
		cur.close()
		return False

	cur.execute('UPDATE company SET money = %s WHERE uid = %s', [updatedMoney, uid])
	cur.connection.commit()
	cur.close()
	return True

@app.route('/promoteTask/<taskid>')
def promoteTask(taskid):
	printUser()
	cur = mysql.connection.cursor()
	cur.execute('SELECT progress FROM tasks WHERE id = %s', [taskid])

	quality = cur.fetchone()['progress']

	cur.execute('UPDATE tasks SET status = %s, progress = %s WHERE id = %s', ["1", "0", taskid])
	cur.connection.commit()
	cur.close()
	return redirect(url_for('office', uid=session['uid']))

@app.route('/sellWork/<workid>')
def sellWork(workid):
	cur = mysql.connection.cursor()
	cur.execute('SELECT * FROM tasks WHERE workid=%s', [workid])
	task = cur.fetchone()

	if task['potential'] > 85 and task['progress'] > 80 and task['progress'] < 130:
		cur.execute("SELECT fans FROM company WHERE uid = %s", [session['uid']])
		fans = cur.fetchone()['fans']
		fans = (task['potential']*50)+fans
		cur.execute("UPDATE company SET fans = %s WHERE uid = %s", [str(fans), session['uid']])
		cur.connection.commit()

	cur.execute('UPDATE tasks SET status = %s WHERE workid = %s', ["11", workid])
	cur.connection.commit()

	companyMoney(int(task['value']),True)

	msg = "Du har nu færdiggjordt {} og dermed har du tjent {} kr.".format(task['title'], str(task['value']))

	flash(msg, 'success')

	cur.close()
	return redirect(url_for('office', uid=session['uid']))

@app.route('/sellTask/<taskid>')
def sellTask(taskid):
	printUser()
	cur = mysql.connection.cursor()

	cur.execute('SELECT * FROM tasks')
	task = cur.fetchone()

	progress = task['progress']
	potential = task['potential']
	quality = task['quality']

	hype = (potential+quality+progress)/3/100

	cur.execute('UPDATE tasks SET status = %s, hype = %s WHERE id = %s', ["2", str(hype), taskid])
	cur.connection.commit()
	cur.close()
	flash('Du har nu sendt dit produkt til produktion.', 'success')
	return redirect(url_for('office', uid=session['uid']))

def getCompanyType():
	cur = mysql.connection.cursor()
	cur.execute("SELECT companytype FROM company WHERE uid=%s", [session['uid']])
	companytype = cur.fetchone()['companytype']
	cur.close()
	return companytype

@app.route('/acceptWork/<workid>')
def acceptWork(workid):
	cur = mysql.connection.cursor()
	cur.execute("SELECT * FROM works WHERE id=%s", [workid])
	work = cur.fetchone()

	potential = str(random.randint(0,100))

	cur.execute('INSERT INTO tasks(workid, title, niveau, payment, status, uid, potential) VALUES(%s, %s, %s, %s, %s, %s, %s)',
				[work['id'], work['title'], work['niveau'], work['payment'] ,"10", session['uid'], potential])

	cur.execute('DELETE FROM works WHERE id= %s', [work['id']])
	cur.connection.commit()

	cur.close()
	return redirect(url_for('office', uid=session['uid']))

@app.route('/createWork', methods=['GET', 'POST'])
def createWork():
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM works')
	if result > 0:
		works = cur.fetchall()
		cur.close()
		return render_template('createWork.html', works=works)
	cur.close()
	flash('Der er ingen nye forespørgelser', 'danger')
	return redirect(url_for('office', uid=session['uid']))

@app.route('/createTask', methods=['GET', 'POST'])
def createTask():
	printUser()
	form = createTaskForm(request.form)

	if (getCompanyType() < 2):
		flash('Du skal opgradere din virksomhedstype for at lave dine egne projekter.', 'danger')
		return redirect(url_for('office', uid=session['uid']))

	if request.method == 'POST' and form.validate():
		taskname = form.taskname.data
		type = form.type.data
		retail = form.retail.data
		niveau = form.niveau.data
		potential = random.randint(20,101)

		if companyMoney(100000,False):
			cur = mysql.connection.cursor()
			cur.execute("INSERT INTO tasks(uid, title, progress, value, type, retail, niveau, potential, status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
						[session['uid'], taskname, "0", "-100000", type, str(retail), str(niveau), potential, "0"])

			cur.connection.commit()
			cur.close()

			flash('Din opgave er sat i værk!', 'success')
			return redirect(url_for('office', uid=session['uid']))


	return render_template('createTask.html', form=form)


def educateAll():
	cur = mysql.connection.cursor()
	result = cur.execute("SELECT * FROM employee")
	if result > 0:
		employees = cur.fetchall()
		for employee in employees:
			employee['concentration'] = random.randint(int(employee['potential']/4), int(employee['potential']/2)*5)

			employee['frontendexp'] += employee['concentration'] * (random.randint(0,3)/3)
			employee['backendexp'] += employee['concentration'] * (random.randint(0,3)/3)
			employee['marketingexp'] += employee['concentration'] * (random.randint(0,3)/3)
			employee['audioexp'] += employee['concentration'] * (random.randint(0,3)/3)
			employee['systemexp'] += employee['concentration'] * (random.randint(0,3)/3)
			employee['graphicexp'] += employee['concentration'] * (random.randint(0,3)/3)

			employee['total'] = 0
			if int(employee['companyid']) != -1:
				print(employee['companyid'])
				if employee['frontendexp'] > 100:
					employee['frontendexp'] = 0.0
					employee['frontend'] += 1
					employee['total'] += 1
				if employee['backendexp'] > 100:
					employee['backendexp'] = 0.0
					employee['backend'] += 1
					employee['total'] += 1
				if employee['marketingexp'] > 100:
					employee['marketingexp'] = 0.0
					employee['marketing'] += 1
					employee['total'] += 1
				if employee['audioexp'] > 100:
					employee['audioexp'] = 0.0
					employee['audio'] += 1
					employee['total'] += 1
				if employee['systemexp'] > 100:
					employee['systemexp'] = 0.0
					employee['system'] += 1
					employee['total'] +=1
				if employee['graphicexp'] > 100:
					employee['graphicexp'] = 0.0
					employee['graphic'] += 1
					employee['total'] +=1


			cur.execute("UPDATE employee SET frontend = %s, backend = %s, marketing = %s, audio = %s, system = %s, graphic = %s, frontendexp = %s, backendexp = %s, marketingexp = %s, audioexp = %s, systemexp = %s, graphicexp = %s WHERE id = %s",
				[employee['frontend'], employee['backend'], employee['marketing'], employee['audio'], employee['system'], employee['graphic'],
				 employee['frontendexp'], employee['backendexp'], employee['marketingexp'], employee['audioexp'], employee['systemexp'], employee['graphicexp'], employee['id']])
			cur.connection.commit()

@app.route('/educate', methods=['GET', 'POST'])
def educate():
	if (getCompanyType() < 3):
		flash('Du skal opgradere din virksomhedstype for holde foredrag.', 'danger')
		return redirect(url_for('office', uid=session['uid']))

	if request.method == 'POST':
		cur = mysql.connection.cursor()
		cur.execute("SELECT coursed FROM company WHERE uid = %s", [session['uid']])
		coursed = cur.fetchone()
		if coursed['coursed'] == 0:
			cur.execute("SELECT education FROM company WHERE uid = %s", [session['uid']])
			education = cur.fetchone()
			result = cur.execute("SELECT * FROM employee WHERE companyid = %s", [session['uid']])
			employees = {}
			if result > 0:
				employees = cur.fetchall()
				for employee in employees:
					employee['concentration'] = random.randint(int(employee['potential']/6), int(employee['potential']/4))*education['education']

					employee['frontendexp'] += employee['concentration'] * (random.randint(0,3)/3)
					employee['backendexp'] += employee['concentration'] * (random.randint(0,3)/3)
					employee['marketingexp'] += employee['concentration'] * (random.randint(0,3)/3)
					employee['audioexp'] += employee['concentration'] * (random.randint(0,3)/3)
					employee['systemexp'] += employee['concentration'] * (random.randint(0,3)/3)
					employee['graphicexp'] += employee['concentration'] * (random.randint(0,3)/3)

					employee['total'] = 0
					if employee['frontendexp'] > 100:
						employee['frontendexp'] = 0.0
						employee['frontend'] += 1
						employee['total'] += 1
					if employee['backendexp'] > 100:
						employee['backendexp'] = 0.0
						employee['backend'] += 1
						employee['total'] += 1
					if employee['marketingexp'] > 100:
						employee['marketingexp'] = 0.0
						employee['marketing'] += 1
						employee['total'] += 1
					if employee['audioexp'] > 100:
						employee['audioexp'] = 0.0
						employee['audio'] += 1
						employee['total'] += 1
					if employee['systemexp'] > 100:
						employee['systemexp'] = 0.0
						employee['system'] += 1
						employee['total'] +=1
					if employee['graphicexp'] > 100:
						employee['graphicexp'] = 0.0
						employee['graphic'] += 1
						employee['total'] +=1

					cur.execute("INSERT INTO concentrations(employeeid, xp) VALUES(%s, %s)", [employee['id'], employee['concentration']])
					cur.execute("UPDATE company SET coursed = %s WHERE uid = %s", ["1", session['uid']])
					cur.execute("UPDATE employee SET frontend = %s, backend = %s, marketing = %s, audio = %s, system = %s, graphic = %s, frontendexp = %s, backendexp = %s, marketingexp = %s, audioexp = %s, systemexp = %s, graphicexp = %s WHERE id = %s",
						[employee['frontend'], employee['backend'], employee['marketing'], employee['audio'], employee['system'], employee['graphic'],
						 employee['frontendexp'], employee['backendexp'], employee['marketingexp'], employee['audioexp'], employee['systemexp'], employee['graphicexp'], employee['id']])
					cur.connection.commit()

			else:
				flash('Du har ingen ansatte', 'danger')

			cur.close()
			return render_template('educate.html', employees=employees)

		else:
			cur.close()
			flash('Du har allerede holdt et foredrag idag', 'danger')
			return render_template('educate.html')


	return render_template('educate.html')

@app.route('/cancelTask/<taskid>')
def cancelTask(taskid):
	printUser()
	cur = mysql.connection.cursor()
	cur.execute("UPDATE tasks SET status = %s WHERE id = %s", ["3", taskid])
	cur.connection.commit()
	cur.close()
	flash('Du har nu fjernet produktet fra salg.', 'success')
	return redirect(url_for('office', uid=session['uid']))

@app.route('/task/<taskid>')
def task(taskid):
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM tasks WHERE id = %s',[taskid])
	if result > 0:
		task = cur.fetchone()
		task['value'] = int(task['value'])
		cur.execute('SELECT companyname FROM company WHERE uid = %s',[task['uid']])
		companyname = cur.fetchone()
		task['companyname'] = companyname['companyname']
		cur.close()


		return render_template('task.html', task=task)

	cur.close()
	return render_template('task.html')

@app.route('/products')
def products():
	cur = mysql.connection.cursor()
	result = cur.execute('SELECT * FROM tasks')
	if result > 0:
		tasks = cur.fetchall()
		for task in tasks:
			task['value'] = int(task['value'])
			task['createdate'] = task['createdate'].date()
			cur.execute('SELECT companyname FROM company WHERE uid = %s',[task['uid']])
			companyname = cur.fetchone()
			task['companyname'] = companyname['companyname']

		cur.close()
		return render_template('products.html', tasks=tasks)
	cur.close()
	return render_template('products.html')


@app.route('/copies/<taskid>', methods=['GET', 'POST'])
def copies(taskid):
	printUser()

	form = copiesForm(request.form)

	if request.method == 'POST' and form.validate():
		amount = form.amount.data
		cur = mysql.connection.cursor()
		cur.execute("SELECT retail, copies, value FROM tasks WHERE id = %s", [taskid])
		result = cur.fetchone()
		retail = result['retail']
		value = result['value']
		copies = result['copies'] + amount
		price = amount*(retail*0.3)
		value -= price
		if companyMoney(price, False):
			msg = "Du har nu købt {} kopier til en samlet pris af {} kr.".format(amount, price)
			flash(msg, 'success')
		else:
			cur.close()
			return render_template('copies.html', form=form)
		cur.execute("UPDATE tasks SET copies = %s, value = %s WHERE id = %s", [copies, value, taskid])
		cur.connection.commit()
		cur.close()
		return redirect(url_for('office', uid=session['uid']))

	return render_template('copies.html', form=form)

def updateTasks(spec = 0):
	with app.app_context():
		cur = mysql.connection.cursor()
		if spec == 29:
			result = cur.execute('SELECT * FROM tasks WHERE uid = %s', [spec])
		else:
			result = cur.execute('SELECT * FROM tasks')
		if result > 0:
			tasks = cur.fetchall()
			for task in tasks:
				progress = task['progress']
				title = task['title']
				type = task['type']
				niveau = task['niveau']
				potential = task['potential']
				reach = task['reach']
				retail = task['retail']
				status = task['status']
				quality = task['quality']
				userid = task['uid']
				copies = task['copies']
				hype = task['hype']
				value = task['value']
				copiessold = task['copiessold']
				payment = task['payment']

				cur.execute("SELECT fans FROM company WHERE uid = %s", [userid])
				fans = cur.fetchone()['fans']

				cur.execute("SELECT COUNT(*) as count FROM tasks WHERE uid = %s", [userid])
				count = cur.fetchone()['count']

				if progress==0:
					progress = 2

				if (progress < 150 and progress > 0 and status == 10):
					delta = (((potential*math.sqrt(30*50)/niveau/24/5)+1)*random.uniform(0.8,1.2))/count
					progress += delta

					if progress < 100:
						value = payment * (progress/100)

					if (progress > 105):
						value = payment * 0.96

					cur.execute('UPDATE tasks SET progress = %s, value = %s WHERE id = %s',[str(progress), str(value),task['id']])
					cur.connection.commit()

				elif (progress < 101 and progress > 0 and status == 0):

					stabforce = getStabSum(userid, "dev")
					if stabforce == 0:
						stabforce = 10

					delta = (potential*math.sqrt(stabforce*50)/niveau/24/24)+1
					progress += delta

					if (progress > 99):
						progress = 100

					quality = progress*math.sqrt(stabforce/300)*random.uniform(0.9,1.3)

					cur.execute('UPDATE tasks SET progress = %s, quality = %s WHERE id = %s',[str(progress), str(quality),task['id']])
					cur.connection.commit()

				elif (progress < 101 and progress > 0 and status == 1):
					stabforce = getStabSum(userid, "mark")
					if stabforce == 0:
						stabforce = 10
					delta = (potential*math.sqrt(stabforce*50)/niveau/24/24)+1
					progress += delta
					if (progress > 99):
						progress = 100

					hype = (potential+quality+progress)/3/100
					reach = potential * hype * math.sqrt(fans*niveau+1)/((retail+1)/5)

					cur.execute('UPDATE tasks SET progress = %s, reach = %s, hype = %s WHERE id = %s',[str(progress), str(reach), str(hype), task['id']])
					cur.connection.commit()
				elif (status == 2):
					stabforce = getStabSum(userid, "sale")
					hype = hype * (random.uniform(97.0,101.4)/100)
					reach = potential * hype * math.sqrt(fans*niveau+1)/((retail+1)/5)*(stabforce/100)

					toSell = random.randint(5,(int(reach/6+6)))

					daily = retail*toSell*46

					if toSell >= copies:
						toSell = copies

					copies = copies - toSell

					copiessold += toSell

					if copies <= 0:
						copies = 0
						daily = 0
						fans = fans * 0.9

					value = value + daily/46

					if fans <= 10:
						fans = 10

					if quality > random.randint(25,65) and potential > random.randint(45,65):
						if fans > 50000:
							fans = fans * (random.uniform(99.9,101.9)/100)
						elif fans > 5000:
							fans = fans + ((fans/50) * (random.randint(98,104)/100))
						else:
							fans = fans * (random.randint(95,125)/100)
					else:
						fans = fans - ((fans/10) * (random.randint(97,107)/100))

					cur.execute('UPDATE tasks SET hype = %s, copies = %s, reach = %s, daily = %s, value=%s, copiessold = %s WHERE id = %s',
												[str(hype), str(copies), str(reach), str(daily), str(value), str(copiessold), task['id']])
					cur.connection.commit()
					#print("Bruger: ", userid , " +", int(daily/48), " Opg: ", title, " Hype: ", hype)

					companyMoney(int(daily/48), True, task['uid'])

					cur.execute('UPDATE company SET fans = %s WHERE uid = %s', [str(fans), userid])
					cur.connection.commit()
				else:
					cur.execute('UPDATE tasks SET progress = %s WHERE id = %s',["1" ,task['id']])
					cur.connection.commit()
		cur.close()

@app.route('/upgradeOffice', methods=['POST','GET'])
def upgradeOffice():
	cur = mysql.connection.cursor()
	cur.execute("SELECT office FROM company WHERE uid = %s", [session['uid']])
	office = cur.fetchone()['office']



	if request.method == 'POST':
		if getCompanyType() < 3:
			flash('Du skal have en større virksomhedstype for at opgradere', 'danger')

		else:
			price = [0, 1000000, 3000000, 10000000, 25000000, 50000000, 100000000, 100000000, 100000000, 100000000]

			if companyMoney(price[office], False):
				cur.execute("UPDATE company SET office=%s WHERE uid = %s", [str(office+1), session['uid']])
				cur.connection.commit()
				flash('Du har nu opgraderet dit kontor', 'success')
				cur.close()
				return redirect(url_for('office', uid=session['uid']))

	cur.close()
	return render_template('upgradeOffice.html', office=office)

@app.route('/upgradeEducation', methods=['GET', 'POST'])
def upgradeEducation():
	cur = mysql.connection.cursor()
	cur.execute("SELECT education FROM company WHERE uid = %s", [session['uid']])
	education = cur.fetchone()['education']



	if request.method == 'POST':
		if getCompanyType() < 3:
			flash('Du skal have en større virksomhedstype for at opgradere', 'danger')
		else:
			price = [0, 1000000, 3000000, 10000000, 25000000, 50000000, 100000000, 100000000, 100000000, 100000000]

			if companyMoney(price[education], False):
				cur.execute("UPDATE company SET education=%s WHERE uid = %s", [str(education+1), session['uid']])
				cur.connection.commit()
				flash('Du har nu opgraderet dit uddannelsesfacilitet', 'success')
				cur.close()
				return redirect(url_for('office', uid=session['uid']))

	cur.close()
	return render_template('upgradeEducation.html', education=education)

@app.route('/upgradeCompany', methods=['GET', 'POST'])
def upgradeCompany():
	cur = mysql.connection.cursor()
	cur.execute("SELECT companytype FROM company WHERE uid = %s", [session['uid']])
	companytype = cur.fetchone()['companytype']


	if request.method == 'POST':
		price = [0, 300000, 1000000, 3000000, 25000000, 50000000, 100000000, 100000000, 100000000, 100000000]

		if companyMoney(price[companytype], False):
			cur.execute("UPDATE company SET companytype=%s WHERE uid = %s", [str(companytype+1), session['uid']])
			cur.connection.commit()
			flash('Du har nu opgraderet din virksomhed', 'success')
			cur.close()
			return redirect(url_for('office', uid=session['uid']))
		cur.close()
		return redirect(url_for('office', uid=session['uid']))

	cur.close()
	return render_template('upgradeCompany.html', companytype=companytype)


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

def resetCourse():
	with app.app_context():
			cur = mysql.connection.cursor()
			cur.execute('UPDATE company SET coursed = %s', ["0"])
			cur.connection.commit()
			cur.close()

def updateSalary():
	with app.app_context():
		cur = mysql.connection.cursor()
		result = cur.execute("SELECT * FROM employee")
		if result > 0:
			employees = cur.fetchall()
			for employee in employees:
				year = int(employee['year'])
				potential = int(employee['potential'])
				sum = int(getStatsSum(employee))
				salary = sum/year*potential*32*random.uniform(0.7,1.3)
				cur.execute("UPDATE employee SET salary = %s WHERE id = %s", [str(salary), employee['id']])
				cur.connection.commit()
		cur.close()

@app.route('/updatealltasks/<updates>')
def updateAllTasks(updates = 1):
	for i in range(0, int(updates)):
		updateTasks(29)
	# newDay()
	# paySalary()
	#updateValuation()
	# createEmployees()
	#educateAll()
	#updateSalary()
	return redirect(url_for('office', uid = session['uid']))

@app.route('/test')
def test():
	createNewWork()
	return redirect(url_for('office', uid = session['uid']))

def updateValuation():
	with app.app_context():
		cur = mysql.connection.cursor()
		result = cur.execute("SELECT * FROM company")
		if result > 0:
			companies = cur.fetchall()
			for company in companies:
				company['sum'] = 0
				result = cur.execute("SELECT sum(value) as sum FROM tasks WHERE uid = %s", [company['uid']])
				if result > 0:
					company['sum'] = cur.fetchone()['sum']
					if company['sum'] == None:
						company['sum'] = 0
					valuation = company['money'] + company['sum']
					cur.execute("INSERT INTO valuations(uid, valuation) VALUES(%s, %s)", [company['uid'], valuation])
					cur.connection.commit()
		cur.close()

def getValuation(uid):
	with app.app_context():
		cur = mysql.connection.cursor()
		valuation = 0
		result = cur.execute("SELECT valuation FROM valuations WHERE uid = %s ORDER BY dato DESC", [uid])
		if result > 0:
			valuation = cur.fetchone()['valuation']
		cur.close()
		return valuation


@app.route('/faq')
def faq():
	return render_template('faq.html')

@app.route('/patchnotes')
def patchnotes():
	return render_template('patchnotes.html')

def printUser():
	with app.app_context():
		cur = mysql.connection.cursor()
		cur.execute("SELECT name FROM user WHERE id = %s", [session['uid']])
		name = cur.fetchone()
		name = name['name']
		print(name, request.environ.get('HTTP_X_REAL_IP', request.remote_addr))
		cur.close()

def createNewWork():
	with app.app_context():
		cur = mysql.connection.cursor()
		cur.execute('SELECT COUNT(*) as amount FROM works')
		amount = cur.fetchone()['amount']

		svær = ['Gå tur med hund', 'Søgefunktion til Microsoft', 'Datascraping hos google', 'Mal plankeværk', 'Slå Græs', 'Ansigsgenkendelse', 'Wordpress side', 'Byg en drone', 'dendanskemetode.dk', 'Søgeoptimering', 'Fotografarbejde', 'Tag 50 snus på en dag challenge']

		if amount < 15:
			for i in range(0, 15-amount%15):
				rand = random.randint(1,3)
				cur.execute('INSERT INTO works(title, niveau, payment) VALUES (%s, %s, %s)', [svær[random.randint(0,len(svær)-1)], str(rand), str(rand*50000)])
				cur.connection.commit()

		cur.close()
		print(amount)


def serverUpdate():
	with app.app_context():
		updateSalary()
		updateValuation()
		paySalary()
		resetCourse()
		newDay()

scheduler.add_job(serverUpdate, 'cron', hour=0)
scheduler.add_job(updateTasks, 'cron', hour='0-23', minute='0,30')
scheduler.add_job(createNewWork, 'cron', hour='0-23', minute='1,31')
scheduler.start()

if __name__ == '__main__':
	app.secret_key='secret123'
	app.run(host='192.168.0.60', threaded=True)
	# app.run(debug='true', host='192.168.0.60', threaded=True)

atexit.register(lambda: scheduler.shutdown())
