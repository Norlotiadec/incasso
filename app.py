from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from config import username, password, host, port, database
import pandas as pd
import calendar
import io


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+mysqldb://{username}:{password}@{host}:{port}/{database}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(200))
    registration_date = db.Column(db.DateTime)

    credits = db.relationship('Credits', backref='users')

    def __repr__(self):
        return f'User {self.id}'


class Credits(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    issuance_date = db.Column(db.DateTime)
    return_date = db.Column(db.DateTime)
    actual_return_date = db.Column(db.DateTime)
    body = db.Column(db.Integer)
    percent = db.Column(db.Float)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    payments = db.relationship('Payments', backref='credits')

    def __repr__(self):
        return f'Credit {self.id}'


class Dictionary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))

    payments = db.relationship('Payments', backref='dictionary')

    def __repr__(self):
        return self.name


class Plans(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.DateTime)
    sum = db.Column(db.Integer)
    category_id = db.Column(db.Integer, db.ForeignKey('dictionary.id'))

    category = db.relationship('Dictionary', backref='plans', uselist=False)

    def __repr__(self):
        return f'Plan {self.id}'


class Payments(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sum = db.Column(db.Float)
    payment_date = db.Column(db.DateTime)
    credit_id = db.Column(db.Integer, db.ForeignKey('credits.id'))
    type_id = db.Column(db.Integer, db.ForeignKey('dictionary.id'))

    def __repr__(self):
        return f'Payment {self.id}'


@app.route('/user_credits/<user_id>')
def get_credits(user_id):
    try:
        user = Users.query.get(user_id)
        info_credits = dict()
        info_credits['user_login'] = user.login
        info_credits['credits'] = list()
        for credit in user.credits:
            credit_dict = dict()
            credit_dict['issuance_date'] = credit.issuance_date
            if credit.actual_return_date:
                credit_dict['close'] = True
                credit_dict['return_date'] = credit.actual_return_date
                credit_dict['body'] = credit.body
                credit_dict['percent'] = credit.percent
                credit_dict['sum_payment'] = round(sum([i.sum for i in credit.payments]), 1)
            else:
                credit_dict['close'] = False
                credit_dict['return_date'] = credit.return_date
                credit_dict['days_loan_overdue'] = (datetime.now().date() - credit.return_date).days
                credit_dict['body'] = credit.body
                credit_dict['percent'] = credit.percent
                credit_dict['body_payments_sum'] = round(sum([i.sum for i in credit.payments if i.type_id == 1]), 2)
                credit_dict['percent_payments_sum'] = round(sum([i.sum for i in credit.payments if i.type_id == 2]), 2)
            if credit_dict:
                info_credits['credits'].append(credit_dict)
        return info_credits
    except Exception as ex:
        return {'Error': f'{ex}'}


@app.route("/upload", methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        raw_data = request.files['file'].read()  # In form data, I used "myfile" as key.
        data = io.BytesIO(raw_data)
        data.seek(0)
        df = pd.read_excel(data)
        list_plans = [(i.period.strftime('%Y-%m-%d'), i.category.name) for i in Plans.query.all()]
        right_file = False
        for item in df.to_dict('records'):
            if (item['місяць плану'].strftime('%Y-%m-%d'), item['назва категорії плану']) in list_plans:
                raise ValueError('Місяць та категорія плану вже наявні в базі даних')
            elif item['місяць плану'].day == 1 and item['сума'] >= 0:
                right_file = True
            else:
                raise ValueError('В місяці плану вказане невірне число або стовпець "сума" містить пусте значення')

        if right_file:
            for item in df.to_dict('records'):
                # print(item)
                # print(Dictionary.query.filter_by(name = item['назва категорії плану']).first().id)
                p = Plans(
                    period=item['місяць плану'],
                    sum=item['сума'],
                    category_id=Dictionary.query.filter_by(name = item['назва категорії плану']).first().id
                )
                db.session.add(p)
            db.session.commit()
            return {'message': 'Дані додані до бази даних'}

    return '''
    <!doctype html>
    <title>Upload an excel file</title>
    <h1>Excel file upload (csv, tsv, csvz, tsvz only)</h1>
    <form action="" method=post enctype=multipart/form-data>
    <p><input type=file name=file><input type=submit value=Upload>
    </form>
    '''


@app.route('/plans_performance', methods=['POST', 'GET'])
def plans_performance():
    """
    KEY for post request: date
    VALUE for example: 20.10.2021
    """
    if request.method == 'POST':
        try:
            current_date = datetime.strptime(request.form['date'], '%d.%m.%Y')
        except:
            return {'Error': 'Невірний формат дати. Спробуйте: %d.%m.%Y'}
        first_day_of_date = date(current_date.year, current_date.month, 1)
        plans = Plans.query.filter_by(period=first_day_of_date).all()
        all_list = list()
        if plans:
            for plan in plans:
                dict_info = dict()
                if plan.category_id == 3:
                    dict_info['period'] = plan.period
                    dict_info['category'] = plan.category.name
                    dict_info['sum'] = plan.sum
                    credits = Credits.query.filter(first_day_of_date<=Credits.issuance_date,
                                                   current_date>=Credits.issuance_date).all()
                    dict_info['amount_loans_issued'] = sum([credit.body for credit in credits])
                    dict_info['success_rate'] = round(dict_info['amount_loans_issued']/dict_info['sum']*100, 2)
                    if dict_info:
                        all_list.append(dict_info)
                elif plan.category_id == 4:
                    dict_info['period'] = plan.period
                    dict_info['category'] = plan.category.name
                    dict_info['sum'] = plan.sum
                    payments = Payments.query.filter(first_day_of_date<=Payments.payment_date,
                                                     current_date>=Payments.payment_date).all()
                    dict_info['amount_of_payments'] = round(sum([payment.sum for payment in payments]), 2)
                    dict_info['success_rate'] = round(dict_info['amount_of_payments']/dict_info['sum']*100, 2)
                    if dict_info:
                        all_list.append(dict_info)

        return all_list
    else:
        return {'Error': 'url працює через POST метод'}


@app.route('/year_performance', methods=['POST', 'GET'])
def year_performance():
    """
    KEY for post request: year
    VALUE for example: 2020
    """
    if request.method == 'POST':
        try:
            current_year = int(request.form['year'])
        except:
            return {'Error': 'Невірний формат року. Спробуйте %Y'}
        first_day_of_year = date(current_year, 1, 1)
        last_day_of_year = date(current_year, 12, 31)
        plans = Plans.query.filter(first_day_of_year<=Plans.period, last_day_of_year>=Plans.period).all()
        sum_lending = sum([i.body for i in Credits.query.filter(first_day_of_year<=Credits.issuance_date,
                                                               last_day_of_year>=Credits.issuance_date).all()])
        sum_payment = round(sum([i.sum for i in Payments.query.filter(first_day_of_year <= Payments.payment_date,
                                                                 last_day_of_year >= Payments.payment_date).all()]), 2)
        list_months = list()
        # amount_loans_issued_year
        months = [[] for _ in range(1, 13)]
        for i in plans:
            months[i.period.month - 1].append(i)

        for plans in months:
            if plans:
                mount_info = dict()
                year = plans[0].period.year
                month = plans[0].period.month
                mount_info['month_year'] = f'Month: {month}, year: {year}'
                last_day_of_month = date(year, month, calendar.monthrange(year, month)[1])
                mount_info['category'] = list()
                for plan in plans:
                    plan_info = dict()
                    if plan.category_id == 3:
                        credits = Credits.query.filter(plan.period<=Credits.issuance_date,
                                                   last_day_of_month>=Credits.issuance_date)
                        plan_info['category'] = plan.category.name
                        plan_info['number_of_lending'] = credits.count()
                        plan_info['sum'] = plan.sum
                        plan_info['amount_loans_issued'] = sum([credit.body for credit in credits.all()])
                        plan_info['success_rate'] = round(plan_info['amount_loans_issued']/plan_info['sum']*100, 2)
                        plan_info['mouth_to_year_percent'] = round(plan_info['amount_loans_issued']/sum_lending*100, 2)
                        if plan_info:
                            mount_info['category'].append(plan_info)
                    elif plan.category_id == 4:
                        plan_info['period'] = plan.period
                        plan_info['category'] = plan.category.name
                        plan_info['sum'] = plan.sum
                        payments = Payments.query.filter(plan.period <= Payments.payment_date,
                                                         last_day_of_month >= Payments.payment_date).all()
                        plan_info['amount_of_payments'] = round(sum([payment.sum for payment in payments]), 2)
                        plan_info['success_rate'] = round(plan_info['amount_of_payments'] / plan_info['sum'] * 100, 2)
                        plan_info['mouth_to_year_percent'] = round(plan_info['amount_of_payments']/sum_payment*100, 2)
                        if plan_info:
                            mount_info['category'].append(plan_info)
            list_months.append(mount_info)
        return list_months

    else:
        return {'Error': 'url працює через POST метод'}


if __name__ == '__main__':
    app.run(debug=True)
