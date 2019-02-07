from wtforms import Form, StringField, TextAreaField, PasswordField, validators, IntegerField, DecimalField, SelectField


class jobTitleForm(Form):
	jobtitle = SelectField('Jobbeskrivelse', choices=[('dev', 'Proggrammør'), ('mark','Markedsføring'), ('kurs','Kursusansvarlig'), ('sale','Sælger'), ('notitle', 'Kaffehenter')])

class copiesForm(Form):
	amount = IntegerField('Antal')

class RegisterForm(Form):
	name = StringField('Fulde navn', [validators.Length(min=1,max=50)])
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
