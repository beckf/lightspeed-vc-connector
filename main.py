from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from mainwindow import Ui_MainWindow
import veracross_api
import lightspeed_api
import sys, getopt
import datetime
import pytz
import config
import csv
from decimal import Decimal, ROUND_HALF_UP
import images
from urllib.parse import quote
import traceback
import requests


class Worker(QRunnable):

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)


class Main(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.threadpool = QThreadPool()
        self.debug_append_log("Multithreading enabled with maximum %d threads." % self.threadpool.maxThreadCount(),
                              "info")

        # Gather Config
        self.config_passwd, ok = QInputDialog.getText(None,
                                                      "Settings Encryption",
                                                      "Enter encryption password for settings.",
                                                      QLineEdit.Password)
        if ok and self.config_passwd:
            print("password=%s" % self.config_passwd)
        try:
            self.c = config.load_settings("config", self.config_passwd)
        except ValueError:
            QMessageBox.question(self, 'Incorrect Encryption Password',
                                       "The password provided will not decrypt the settings.",
                                       QMessageBox.Ok)

        self.vc = veracross_api.Veracross(self.c)
        self.ls = lightspeed_api.Lightspeed(self.c)

        # Shop Name
        self.shop_name = self.get_shop_name()

        # Timezone stuff
        self.shop_timezone_name = self.get_timezone()
        self.timezone = pytz.timezone(self.shop_timezone_name)
        self.shop_timezone_utc_offset = datetime.datetime.now(self.timezone).strftime('%z')
        self.shop_timezone_utc_offset_iso = self.shop_timezone_utc_offset[:3] + ":" + self.shop_timezone_utc_offset[3:]
        self.debug_append_log("Found %s timezone for shop named %s." % (self.shop_timezone_name, self.shop_name),
                              "info")

        # Store data
        self.export_dir = ""
        self.ls_customer_types = dict()
        self.ls_payment_types = dict()

        # Images
        self.ui.lbl_Icon.setPixmap(QPixmap(":/images/icon.png"))

        # Buttons
        self.ui.btn_SyncAllUsers.clicked.connect(self.create_update_customer_worker)
        self.ui.btn_DeleteVCUsers.clicked.connect(self.delete_customer_worker)
        self.ui.btn_ExportFolderPicker.clicked.connect(self.select_export_directory)
        self.ui.btn_ExportCharges.clicked.connect(self.export_charge_balance_worker)
        self.ui.btn_GetCustomerTypes.clicked.connect(self.get_customer_types)
        self.ui.btn_GetPaymentTypes.clicked.connect(self.get_payment_types)
        self.ui.btn_Authorize.clicked.connect(self.authorize_app)
        self.ui.btn_ChangeEncPassword.clicked.connect(self.change_password)
        self.ui.btn_SaveLog.clicked.connect(self.save_log_to_file)

        # Settings Buttons
        self.ui.btn_SaveSettings.clicked.connect(self.save_settings_button)

        # Export Tab
        self.ui.chk_ClearCharges.setChecked(False)

        # Export Options Buttons
        self.ui.btn_SaveExportOptions.clicked.connect(self.save_settings_button)

        # Action Menu
        self.ui.actionQuit.triggered.connect(self.close)

        # UI Setup
        self.ui.txt_SettingsFileLocation.setText(str(config.config_file_location()))
        self.ui.combo_CustomerType.clear()
        self.ui.combo_CustomerType.addItems([''])
        self.ui.combo_PaymentType.clear()
        self.ui.combo_PaymentType.addItems([''])
        self.ui.dateEdit_BeginExportRange.setDateTime(QDateTime.currentDateTime())
        self.ui.dateEdit_EndExportRange.setDateTime(QDateTime.currentDateTime())
        self.ui.dateEdit_SyncUpdatedAfterDate.setDateTime(QDateTime.currentDateTime())

        if "vcuser" in self.c.keys():
            self.ui.txt_VCUser.setText(self.c["vcuser"])
        if "vcpass" in self.c.keys():
            self.ui.txt_VCPass.setText(self.c["vcpass"])
        if "vcurl" in self.c.keys():
            self.ui.txt_VCAPIURL.setText(self.c["vcurl"])
        if "client_id" in self.c.keys():
            self.ui.txt_LSDevelID.setText(self.c["client_id"])
            self.ui.lbl_AuthorizeApp.setText("<a href=\"https://cloud.lightspeedapp.com/oauth/authorize.php"
                                             "?response_type=code&client_id={}&scope=employee:all\">"
                                             "Authorize Link</a>".format(self.c["client_id"]))
        if "client_secret" in self.c.keys():
            self.ui.txt_DevelSecret.setText(self.c["client_secret"])
        if "refresh_token" in self.c.keys():
            self.ui.txt_RefreshToken.setText(self.c["refresh_token"])
        if "account_id" in self.c.keys():
            self.ui.txt_LSAccountID.setText(self.c["account_id"])
        if "vc_export_catalog_item_fk" in self.c.keys():
            self.ui.txt_ExportOptionsCatalog_Item_fk.setText(self.c["vc_export_catalog_item_fk"])
        if "vc_export_school_year" in self.c.keys():
            self.ui.txt_ExportOptionsSchoolYear.setText(self.c["vc_export_school_year"])
        if "vc_export_transaction_type" in self.c.keys():
            self.ui.txt_ExportOptionsTransactionType.setText(self.c["vc_export_transaction_type"])
        if "vc_export_transaction_source" in self.c.keys():
            self.ui.txt_ExportOptionsTransactionSource.setText(self.c["vc_export_transaction_source"])

        # Set Active Tab to Sync
        self.ui.tabs.setCurrentIndex(0)

        # Get some initial LS Data
        self.get_customer_types()
        self.get_payment_types()

        # Get License
        self.get_license()

    def create_update_customer_worker(self):
        """
        Threaded trigger for the create_update_customer method below.
        :return:
        """
        worker = Worker(self.create_update_customer)
        worker.signals.finished.connect(self.create_update_customer_complete)
        self.threadpool.start(worker)

    def create_update_customer_complete(self):
        """
        Signal when create_update_customer is complete
        :return:
        """
        self.debug_append_log("User Sync Complete.", "info")

    def create_update_customer(self):

        if self.ui.checkBox_SyncChangesAfterDate.isChecked():
            updated_after_ui = self.ui.dateEdit_SyncUpdatedAfterDate.date()
            param = "updated_after={}".format(updated_after_ui.toPyDate())
        else:
            param = False

        if self.ui.combo_SyncVCUserType.currentText() == "Students":
            self.debug_append_log("Getting Veracross Students (Current)", "info")
            if param:
                param = "option=2," + param
            else:
                param = "option=2"
            vcdata = self.vc.pull("students", parameters=param)
            ls_customerTypeID = self.ls_customer_types["Student"]
        elif self.ui.combo_SyncVCUserType.currentText() == "Faculty Staff":
            self.debug_append_log("Getting Veracross Faculty Staff (Faculty and Staff)", "info")
            if param:
                param_extended = param + "&roles=1,2"
                vcdata = self.vc.pull("facstaff", parameters=param_extended)
            else:
                vcdata = self.vc.pull("facstaff", "roles=1,2")
            ls_customerTypeID = self.ls_customer_types["FacultyStaff"]
        else:
            self.debug_append_log("Select Veracross User Type first.", "info")
            return None

        for i in vcdata:
            if str(i["current_grade"]) == self.ui.combo_SyncGradeLevel.currentText() or \
                    self.ui.combo_SyncGradeLevel.currentText() == "None":
                hh = self.vc.pull("households/" + str(i["household_fk"]))
                h = hh["household"]
                param = dict(load_relations='all', limit=1, companyRegistrationNumber=str(i["person_pk"]))
                check_current = self.ls.get("Customer", parameters=param)

                vc_formatted = {'Customer':
                                    {'firstName': '',
                                     'lastName': i["last_name"],
                                     'companyRegistrationNumber': i["person_pk"],
                                     'customerTypeID': ls_customerTypeID,
                                     'Contact': {
                                         'custom': '',
                                         'noEmail': 'false',
                                         'noPhone': 'false',
                                         'noMail': 'false',
                                         'Emails': {
                                             'ContactEmail': {
                                                 'address': i["email_1"],
                                                 'useType': 'Primary'
                                             }
                                         },
                                         'Addresses': {
                                             'ContactAddress': {
                                                 'address1': h["address_1"],
                                                 'address2': h["address_2"],
                                                 'city': h["city"],
                                                 'state': h["state_province"],
                                                 'zip': h["postal_code"],
                                                 'country': h["country"],
                                                 'countryCode': '',
                                                 'stateCode': ''
                                             }
                                         }
                                     },
                                     'CreditAccount': {
                                         'creditLimit': '5000.00'
                                     },
                                     'CustomFieldValues': {
                                         'CustomFieldValue': [{
                                             'customFieldID': '1',
                                             'value': i["person_pk"]
                                         }, {
                                             'customFieldID': '2',
                                             'value': str(datetime.datetime.now())
                                         }
                                         ]}
                                     }
                                }
                # Update data to use correct nick name format from VC.
                if 'nick_first_name' in i:
                    vc_formatted['Customer']['firstName'] = i['nick_first_name']
                elif 'first_nick_name' in i:
                    vc_formatted['Customer']['firstName'] = i['first_nick_name']

                if int(check_current["@attributes"]["count"]) >= 1:

                    vc_person = dict()
                    ls_customer = dict()

                    # Format VC Data for comparison
                    vc_person["last_name"] = i["last_name"]
                    if 'nick_first_name' in i:
                        vc_person["first_name"] = i['nick_first_name']
                    elif 'first_nick_name' in i:
                        vc_person["first_name"] = i['first_nick_name']
                    vc_person["email"] = i["email_1"]
                    vc_person["address_1"] = h["address_1"]
                    if h["address_2"] is None:
                        vc_person["address_2"] = ''
                    else:
                        vc_person["address_2"] = h["address_2"]
                    vc_person["city"] = h["city"]
                    vc_person["zip"] = h["postal_code"]
                    vc_person["state"] = h["state_province"]

                    # Format LS Data for comparison
                    ls_customer["last_name"] = check_current["Customer"]["lastName"]
                    ls_customer["first_name"] = check_current["Customer"]["firstName"]

                    # Handle missing email addresses.
                    try:
                        ls_customer["email"] = check_current["Customer"]["Contact"]["Emails"]["ContactEmail"]["address"]
                    except:
                        ls_customer["email"] = ''

                    # Handle missing mailing addresses
                    try:
                        ls_customer["address_1"] = check_current["Customer"]["Contact"]["Addresses"]["ContactAddress"]["address1"]
                        ls_customer["address_2"] = check_current["Customer"]["Contact"]["Addresses"]["ContactAddress"]["address2"]
                        ls_customer["city"] = check_current["Customer"]["Contact"]["Addresses"]["ContactAddress"]["city"]
                        ls_customer["zip"] = check_current["Customer"]["Contact"]["Addresses"]["ContactAddress"]["zip"]
                        ls_customer["state"] = check_current["Customer"]["Contact"]["Addresses"]["ContactAddress"]["state"]
                    except:
                        ls_customer["address_1"] = ''
                        ls_customer["address_2"] = ''
                        ls_customer["city"] = ''
                        ls_customer["zip"] = ''
                        ls_customer["state"] = ''

                    # Compare the data
                    if not ls_customer == vc_person:
                        self.debug_append_log("Updating customer {} {}.".format(vc_formatted['Customer']['firstName'],
                                                                                    vc_formatted['Customer']['lastName']),
                                              "info")
                        vc_formatted['Customer']['customerID'] = check_current['Customer']['customerID']
                        self.ls.update("Customer/" + vc_formatted['Customer']['customerID'], vc_formatted["Customer"])
                    else:
                        self.debug_append_log("Record {} {} already up to date.".format(vc_formatted['Customer']['firstName'],
                                                                                vc_formatted['Customer']['lastName']),
                                              "info")
                else:
                    # Add new user when not found in LS
                    new_customer = self.ls.create("Customer", vc_formatted["Customer"])
                    self.debug_append_log("New Customer # {} Added: {} {}".format(new_customer['Customer']['customerID'],
                                                                                  new_customer['Customer']['firstName'],
                                                                                  new_customer['Customer']['lastName']),
                                          "info")

    def delete_customer_worker(self):
        """
        Threaded trigger for the delete_customer method below.
        :return:
        """
        worker = Worker(self.delete_customer)
        worker.signals.finished.connect(self.delete_customer_complete)
        self.threadpool.start(worker)

    def delete_customer_complete(self):
        """
        Signal for when delete_customer is complete.
        :return:
        """
        self.debug_append_log("Inactive user delete complete.", "info")

    def delete_customer(self):
        """
        Delete records in Lightspeed.  Filters customers to those that have a companyRegistrationNumber
        :return:
        """
        self.debug_append_log("Checking for customers to delete.", "info")

        valid_vc_ids = []
        for i in self.vc.pull("facstaff", "roles=1,2"):
            valid_vc_ids.append(i["person_pk"])
        for i in self.vc.pull("students", "option=2"):
            valid_vc_ids.append(i["person_pk"])

        current_customers = self.ls.get("Customer", dict(load_relations="all"))

        for i in current_customers["Customer"]:
            if i["companyRegistrationNumber"] != '':
                if int(i["companyRegistrationNumber"]) not in valid_vc_ids:
                    if float(i["CreditAccount"]["balance"]) <= 0:
                        if self.ui.checkBox_SyncSimulateDelete.isChecked():
                            self.debug_append_log("Customer {} {} would normally be deleted (Simulation)".format(
                                i["firstName"], i["lastName"]), "info")
                        else:
                            self.debug_append_log("Deleting customer {} {}".format(i["firstName"], i["lastName"]), "info")
                            self.ls.delete("Customer/" + i["customerID"])
                    else:
                        self.debug_append_log("Cannot delete customer {}, {} {} with credit balance.".format(i["customerID"],
                                                                                                             i["firstName"],
                                                                                                             i["lastName"]),
                                              "info")

    def export_charge_balance_worker(self):
        """
        Threaded trigger for the export_charge method below.
        :return:
        """
        worker = Worker(self.export_charge_balance)
        worker.signals.finished.connect(self.export_charge_balance_complete)
        self.threadpool.start(worker)

    def export_charge_balance_complete(self):
        """
        Signal for when export_charge is complete.
        :return:
        """
        self.debug_append_log("File export complete.", "info")

    def export_charge_balance(self):
        """
        Export Charges from LS in CSV
        :return:
        """
        ct = str(self.ui.combo_CustomerType.currentText())
        ct_id = self.ls_customer_types[ct]

        if self.ui.chk_ClearCharges.isChecked():
            pt = str(self.ui.combo_PaymentType.currentText())
            pt_id = self.ls_payment_types[pt]

        # Ensure there is an export location
        if len(self.ui.line_ExportFolder.text()) == 0:
            self.debug_append_log("Missing export folder location.", "info")
            self.select_export_directory()

        # Notify UI
        self.debug_append_log("Export started for customer type: " + str(ct), "info")

        # !! Sale Line Export !!

        # Export SaleLine Data
        if self.ui.chk_ExportSaleLinesEnabled.isChecked():
            begin_date_ui = self.ui.dateEdit_BeginExportRange.date()
            begin_date = begin_date_ui.toPyDate()
            end_date_ui = self.ui.dateEdit_EndExportRange.date()
            end_date = end_date_ui.toPyDate()

            if len(str(begin_date)) != 10 or len(str(end_date)) != 10:
                self.debug_append_log("Invalid begin or end date.", "info")
                self.debug_append_log(str(begin_date), "info")
                return None

            try:
                parameters = {}
                parameters['load_relations'] = 'all'
                parameters['completed'] = 'true'
                parameters['timeStamp'] = '{},{}T00:00:00-04:00,{}T23:59:59{}'.format("><",
                                                                                      begin_date,
                                                                                      end_date,
                                                                                      self.shop_timezone_utc_offset_iso)
                self.debug_append_log("Querying Lightspeed \"Sales\" data point with parameters " + str(parameters),
                                      "debug")
                salelines = self.ls.get("Sale", parameters=parameters)
            except:
                salelines = None
                self.debug_append_log("Unable to get SaleLine data.", "info")

            saleline_export_data = []

            # throw down some headers.
            f = ['person_id',
                 'customer_account_number',
                 'customer_name',
                 'transaction_source',
                 'transaction_type',
                 'school_year',
                 'item_date',
                 'catalog_item_fk',
                 'description',
                 'quantity',
                 'unit_price',
                 'purchase_amount',
                 'tax_amount',
                 'total_amount',
                 'pos_transaction_id'
                 ]

            # Add debug fields if requested
            if self.ui.chk_DebugExport.isChecked():
                f.append('timestamp')

            saleline_export_data.append(f)

            for i in salelines['Sale']:
                # Does this invoice have a payment that is on account.
                # Hopefully it is not a multi-tender transaction, but just in case...

                on_account = False

                if 'SalePayments' in i:
                    if isinstance(i['SalePayments']['SalePayment'], list):
                        for p in i['SalePayments']['SalePayment']:
                            if p['PaymentType']['code'] == 'SCA':
                                on_account = True
                    else:
                        if i['SalePayments']['SalePayment']['PaymentType']['code'] == 'SCA':
                            on_account = True

                if 'SaleLines' in i and on_account is True:

                    # Check this is a customer we requested.
                    if i['Customer']['customerTypeID'] != ct_id:
                        continue

                    if isinstance(i['SaleLines']['SaleLine'], list):
                        for s in i['SaleLines']['SaleLine']:
                            try:
                                saleline_single = [str(i['Customer']['companyRegistrationNumber']),
                                                   str(i['Customer']['companyRegistrationNumber']),
                                                   str(i['Customer']['firstName'] + " " + i['Customer']['lastName']),
                                                   self.ui.txt_ExportOptionsTransactionSource.text(),
                                                   self.ui.txt_ExportOptionsTransactionType.text(),
                                                   self.ui.txt_ExportOptionsSchoolYear.text(),
                                                   str(i['timeStamp'][:10]),
                                                   self.ui.txt_ExportOptionsCatalog_Item_fk.text(),
                                                   str(s['Item']['description']),
                                                   str(s['unitQuantity']),
                                                   Decimal(s['unitPrice']) -
                                                   (Decimal(s['calcLineDiscount']) / int(s['unitQuantity'])),
                                                   Decimal(s['displayableSubtotal']),
                                                   self.roundup_decimal(Decimal(s['calcTax1'])),
                                                   self.roundup_decimal(Decimal(s['calcTotal'])),
                                                   str(i['saleID'])
                                                   ]

                                # Debug fields
                                if self.ui.chk_DebugExport.isChecked():
                                    saleline_single.append(str(i['timeStamp']))

                                saleline_export_data.append(saleline_single)
                            except:
                                self.debug_append_log("Unable to append multiple SaleLine data to CSV.", "info")
                    else:
                        try:
                            if 'Item' in i["SaleLines"]["SaleLine"]:
                                saleline_single = [str(i['Customer']['companyRegistrationNumber']),
                                                   str(i['Customer']['companyRegistrationNumber']),
                                                   str(i['Customer']['firstName'] + " " + i['Customer']['lastName']),
                                                   self.ui.txt_ExportOptionsTransactionSource.text(),
                                                   self.ui.txt_ExportOptionsTransactionType.text(),
                                                   self.ui.txt_ExportOptionsSchoolYear.text(),
                                                   str(i["SaleLines"]["SaleLine"]['timeStamp'][:10]),
                                                   self.ui.txt_ExportOptionsCatalog_Item_fk.text(),
                                                   str(i["SaleLines"]["SaleLine"]['Item']['description']),
                                                   str(i["SaleLines"]["SaleLine"]['unitQuantity']),
                                                   Decimal(i["SaleLines"]["SaleLine"]['unitPrice']) -
                                                   (Decimal(i["SaleLines"]["SaleLine"]['calcLineDiscount']) /
                                                    int(i["SaleLines"]["SaleLine"]['unitQuantity'])),
                                                   Decimal(i["SaleLines"]["SaleLine"]['displayableSubtotal']),
                                                   self.roundup_decimal(
                                                       Decimal(i["SaleLines"]["SaleLine"]['calcTax1'])),
                                                   self.roundup_decimal(
                                                       Decimal(i["SaleLines"]["SaleLine"]['calcTotal'])),
                                                   str(i['saleID'])
                                                   ]
                                # Debug fields
                                if self.ui.chk_DebugExport.isChecked():
                                    saleline_single.append(str(i["SaleLines"]["SaleLine"]['timeStamp']))

                                saleline_export_data.append(saleline_single)
                        except:
                            self.debug_append_log("Unable to append single saleline for sale # " + str(i['saleID']),
                                                  "info")

            try:
                filename = str(self.ui.line_ExportFolder.text())
                filename = filename + '/lightspeed_salelines_export_' + \
                           str(ct) + \
                           "_" + \
                           datetime.datetime.now().strftime('%s') + '.csv'
                filepath = open(filename, 'w')
                with filepath:
                    writer = csv.writer(filepath)
                    for row in saleline_export_data:
                        writer.writerow(row)
            except:
                self.debug_append_log("Failed to export CSV salelines data.", "info")
                return None

        # !! Account Balance Export !!
        try:
            # Get Customers with Balance on Account. Used to export balances and clear accounts.
            customers = self.ls.get("Customer", parameters=dict(load_relations='["CreditAccount"]'))
        except:
            self.debug_append_log("Unable to get Customer data from Lightspeed.", "info")
            return None

        try:
            export_data = []

            f = ['first_name',
                 'last_name',
                 'veracross_id',
                 'lightspeed_cust_type',
                 'balance',
                 'lightspeed_cust_num']

            export_data.append(f)

            for i in customers['Customer']:
                if 'CreditAccount' in i:
                    if (float(i['CreditAccount']['balance']) > 0) and (int(i['customerTypeID']) == int(ct_id)):
                        a = [i['firstName'],
                             i['lastName'],
                             i['companyRegistrationNumber'],
                             i['customerTypeID'],
                             i['CreditAccount']['balance'],
                             i['customerID']]
                        export_data.append(a)

                        if self.ui.chk_ClearCharges.isChecked():
                            # Clear the balance for this account
                            self.clear_account_balances(int(i['customerID']),
                                                        float(i['CreditAccount']['balance']),
                                                        int(pt_id),
                                                        int(i["creditAccountID"]))

        except:
            self.debug_append_log("Failed to format CSV data.", "info")
            return None

        try:
            filename = str(self.ui.line_ExportFolder.text())
            filename = filename + '/lightspeed_balance_export_' + \
                       str(ct) +\
                       "_" +\
                       datetime.datetime.now().strftime('%s') + '.csv'
            filepath = open(filename, 'w')
            with filepath:
                writer = csv.writer(filepath)
                for row in export_data:
                    writer.writerow(row)
        except:
            self.debug_append_log("Failed to export CSV balance data.", "info")
            return None

    def clear_account_balances(self, customerID, balance, paymentID, creditAccountID):
        try:
            formatted_request = {
                                "employeeID": 1,
                                "registerID": 1,
                                "shopID": 1,
                                "customerID": customerID,
                                "completed": 'true',
                                "SaleLines": {
                                    "SaleLine": {
                                        "itemID": 0,
                                        "note": "Balance Cleared by Export",
                                        "unitQuantity": 1,
                                        "unitPrice": -float(balance),
                                        "taxClassID": 0,
                                        "avgCost": 0,
                                        "fifoCost": 0
                                    }
                                },
                                "SalePayments": {
                                    "SalePayment": {
                                        "amount": -float(balance),
                                        "paymentTypeID": paymentID,
                                        "creditAccountID": creditAccountID
                                    }
                                }
                            }
        except:
            self.debug_append_log("Unable to format data to clear balances.", "info")

        try:
            self.ls.create('Sale', data=formatted_request)
            self.debug_append_log("Cleared balance of {} of customerID {}".format(str(balance), str(customerID)),
                                  "info")
        except:
            self.debug_append_log("Unable to clear balance for customerID {}".format(str(customerID)), "info")

    def get_customer_types(self):
        try:
            ct = self.ls.get("CustomerType")
            for i in ct['CustomerType']:
                self.ls_customer_types[i["name"]] = i["customerTypeID"]
        except:
            self.debug_append_log("Cannot get customer types from API, or none exist.", "info")
        # Update UI
        try:
            self.ui.combo_CustomerType.clear()
            self.ui.combo_CustomerType.addItems(self.ls_customer_types.keys())
        except:
            self.debug_append_log("Error getting customer types.", "info")

    def get_payment_types(self):
        try:
            pt = self.ls.get("PaymentType")
            for i in pt['PaymentType']:
                self.ls_payment_types[i["name"]] = i["paymentTypeID"]
        except:
            self.debug_append_log("Cannot get payment types from API.", "info")

        # Update UI
        try:
            self.ui.combo_PaymentType.clear()
            self.ui.combo_PaymentType.addItems(self.ls_payment_types.keys())
        except:
            self.debug_append_log("Error getting payment types.", "info")

        try:
            self.ui.combo_PaymentType.setCurrentIndex(self.ui.combo_PaymentType.findText("Credit Account"))
        except:
            self.debug_append_log("Unable to set default payment type to Credit Account.", "info")

    def get_timezone(self):
        try:
            shop_tz = self.ls.get("Shop")
            return shop_tz["Shop"]["timeZone"]
        except:
            self.debug_append_log("Error getting shop timezone. Using UTC.", "info")
            return "UTC"

    def get_shop_name(self):
        try:
            shop_tz = self.ls.get("Shop")
            return shop_tz["Shop"]["name"]
        except:
            self.debug_append_log("Error getting shop name.", "info")
            return "Unknown Shop Name"

    def authorize_app(self):
        """
        Authorize App
        :return:
        """
        if len(self.ui.txt_CodeReturned.text()) > 0:
            token = self.ls.get_authorization_token(self.ui.txt_CodeReturned.text())
            self.ui.txt_AuthorizeReturnedRefreshToken.setText(str(token))

    def debug_append_log(self, text, level):
        """
        Write to log window
        :param text:
        :return:
        """
        if level is "debug" and self.ui.chk_DebugExport.isChecked():
            self.ui.txtb_SyncLog.append(text)
        if level is "info":
            self.ui.txtb_SyncLog.append(text)

    def roundup_decimal(self,x):
        """
        Self-Explanatory
        :param x: rounded up decimal to two places.
        :return:
        """
        return x.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)

    def select_export_directory(self):
        self.export_dir = QFileDialog.getExistingDirectory(self, 'Select Directory for Export')
        self.ui.line_ExportFolder.setText(self.export_dir)

    def save_log_to_file(self):
        log_dir = QFileDialog.getExistingDirectory(self, 'Select Directory to Save Log')
        filename = log_dir + str("/LSVCConnector.log")
        filepath = open(filename, 'w')
        with filepath:
            filepath.write(self.ui.txtb_SyncLog.toPlainText())

    def save_settings_button(self):
        """
        Save settings
        :return:
        """
        settings = {
            "vcuser": self.ui.txt_VCUser.text(),
            "vcpass": self.ui.txt_VCPass.text(),
            "vcurl": self.ui.txt_VCAPIURL.text(),
            "account_id": self.ui.txt_LSAccountID.text(),
            "refresh_token": self.ui.txt_RefreshToken.text(),
            "client_secret": self.ui.txt_DevelSecret.text(),
            "client_id": self.ui.txt_LSDevelID.text(),
            "vc_export_catalog_item_fk": self.ui.txt_ExportOptionsCatalog_Item_fk.text(),
            "vc_export_school_year": self.ui.txt_ExportOptionsSchoolYear.text(),
            "vc_export_transaction_type": self.ui.txt_ExportOptionsTransactionType.text(),
            "vc_export_transaction_source": self.ui.txt_ExportOptionsTransactionSource.text()
        }
        # Save settings
        config.save_settings(settings, "config", self.config_passwd)
        # Reload Settings
        self.c = config.load_settings("config", self.config_passwd)

        # Suggest user restart the app
        QMessageBox.question(self, 'Settings Saved',
                             "The settings have been saved. It is recommended that "
                             "you quit and restart the application.",
                             QMessageBox.Ok)

    def change_password(self):
        if len(self.ui.txt_ChangeUpdatePassword.text()) >= 10:
            new_password = self.ui.txt_ChangeUpdatePassword.text()
            config.change_password(self.config_passwd, new_password)
            self.config_passwd = new_password
            QMessageBox.question(self, 'Password Updated.', 'The password has now been changed to: {}'.format(new_password),
                                 QMessageBox.Ok)
        else:
            QMessageBox.question(self, 'Password Too Short.',
                                 'The password specified is too short.',
                                 QMessageBox.Ok)

    def get_license(self):
        try:
            r = requests.get('https://raw.githubusercontent.com/beckf/lightspeed-vc-connector/master/LICENSE',
                             allow_redirects=True)
            self.ui.textBrowser_License.setText(r.text)
        except:
            self.ui.textBrowser_License.setText("Unable to connect to the internet.")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Main()
    window.show()
    sys.exit(app.exec_())