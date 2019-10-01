from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineView
from mainwindow import Ui_MainWindow
import veracross_api
import lightspeed_api
import sys
import os
import datetime
import pytz
import config
import csv
from decimal import Decimal, ROUND_HALF_UP
import images
import traceback
import update


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


class AuthorizeLS(QMainWindow):
    def __init__(self, auth_url):
        QMainWindow.__init__(self)
        self.auth_url = auth_url
        self.page = QWebEnginePage()
        self.view = QWebEngineView()
        self.view.setPage(self.page)
        self.interceptor = AuthCodeInterceptor()
        self.page.profile().setRequestInterceptor(self.interceptor)
        self.view.setUrl(QUrl(self.auth_url))
        self.view.show()

    def check_code(self):
        return self.interceptor.code


class AuthCodeInterceptor(QWebEngineUrlRequestInterceptor):
    code_returned = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.code = ""

    def interceptRequest(self, info):
        url = info.firstPartyUrl().toString()

        if "localhost" in url:
            code = url.split("code=")[1]
            self.code = code
            self.code_returned.emit()


class Main(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.threadpool = QThreadPool()
        self.debug_append_log("Multithreading enabled with maximum %d threads." % self.threadpool.maxThreadCount(),
                              "info")

        # Output some debug stuff for cmdline
        try:
            self.working_dir = sys._MEIPASS
        except AttributeError:
            self.working_dir = os.getcwd()

        # Gather Config
        if config.check_enc() is True:
            self.config_passwd, ok = QInputDialog.getText(None,
                                                          "Settings Encryption Password",
                                                          "Enter encryption password to unlock settings.",
                                                          QLineEdit.Password)
        else:
            self.config_passwd, ok = QInputDialog.getText(None,
                                                          "New Settings File Encryption Password",
                                                          "Enter the encryption password that will be "
                                                          "used to encrypt the settings file.",
                                                          QLineEdit.Password)

        if ok and self.config_passwd:
            try:
                self.c = config.load_settings("config", self.config_passwd)
            except ValueError:
                QMessageBox.question(self, 'Incorrect Encryption Password',
                                           "The password provided will not decrypt the settings.",
                                           QMessageBox.Ok)

        self.vc = veracross_api.Veracross(self.c)
        self.ls = lightspeed_api.Lightspeed(self.c)

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

        # Keyboard Shortcuts
        self.key_reveal_hidden_settings = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        self.key_reveal_hidden_settings.activated.connect(self.reveal_hidden)



        if "vcuser" in self.c.keys():
            self.ui.txt_VCUser.setText(self.c["vcuser"])
        if "vcpass" in self.c.keys():
            self.ui.txt_VCPass.setText(self.c["vcpass"])
        if "vcurl" in self.c.keys():
            self.ui.txt_VCAPIURL.setText(self.c["vcurl"])
        if "client_id" in self.c.keys():
            self.ui.txt_LSDevelID.setText(self.c["client_id"])
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
        if "debug_export" in self.c.keys():
            if self.c["debug_export"] is True:
                self.ui.chk_DebugExport.setChecked(True)

        # Store data
        self.export_dir = ""
        self.ls_customer_types = dict()
        self.ls_payment_types = dict()
        self.ls_shops = dict()
        self.ls_employee = dict()

        # Get some initial LS Data
        self.get_customer_types()
        self.get_payment_types()
        self.get_shops()
        self.get_employees()

        # Set Active Tab to Sync
        self.ui.tabs.setCurrentIndex(0)

        # Get License
        self.get_license()

        # Get Version Info
        self.version = update.Update()
        try:
            self.ui.label_VersionInfo.setText(self.version.current_version)
        except:
            self.ui.label_VersionInfo.setText("Version Unknown")

        # Check for Updates
        try:
            if self.version.update_avail():
                self.debug_append_log("Updated Version Available!", "info")
        except:
            self.debug_append_log("Error checking for updates.", "debug")

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

        param = {}

        if self.ui.checkBox_SyncChangesAfterDate.isChecked():
            updated_after_ui = self.ui.dateEdit_SyncUpdatedAfterDate.date()
            param.update({"updated_after": str(updated_after_ui.toPyDate())})

        if self.ui.combo_SyncVCUserType.currentText() == "Students":
            self.debug_append_log("Getting Veracross Students (Current)", "info")

            # Add a grade level filter
            if not self.ui.combo_SyncGradeLevel.currentText() == "None":
                if "Other" in self.ui.combo_SyncGradeLevel.currentText():
                    # Append non-standard grades to the grade_level param. 20-30
                    param.update({"grade_level": ",".join(str(x) for x in list(range(20, 30)))})
                else:
                    param.update({"grade_level": self.ui.combo_SyncGradeLevel.currentText()})

            # Limit to only current students
            param.update({"option": "2"})

            self.debug_append_log("VC Parameters: " + str(param), "debug")
            vcdata = self.vc.pull("students", parameters=param)
            ls_customerTypeID = self.ls_customer_types["Student"]

        elif self.ui.combo_SyncVCUserType.currentText() == "Faculty Staff":
            self.debug_append_log("Getting Veracross Faculty Staff (Faculty and Staff)", "info")
            param.update({"roles": "1,2"})
            self.debug_append_log("VC Parameters: " + str(param), "debug")
            vcdata = self.vc.pull("facstaff", parameters=param)
            ls_customerTypeID = self.ls_customer_types["FacultyStaff"]

        else:
            self.debug_append_log("Select Veracross User Type first.", "info")
            return None

        for i in vcdata:

            hh = self.vc.pull("households/" + str(i["household_fk"]))
            h = hh["household"]
            lsparam = dict(load_relations='all', limit=1, companyRegistrationNumber=str(i["person_pk"]))
            check_current = self.ls.get("Customer", parameters=lsparam)
            # Format data. First name will format later.
            vc_formatted = {'Customer':
                                {'firstName': '',
                                 'lastName': i["last_name"],
                                 'companyRegistrationNumber': i["person_pk"],
                                 'customerTypeID': ls_customerTypeID,
                                 'Contact': {
                                     'custom': i["person_pk"],
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
                vc_person["personpk"] = str(i["person_pk"])
                vc_person["last_name"] = i["last_name"]
                if 'nick_first_name' in i:
                    vc_person["first_name"] = i['nick_first_name']
                elif 'first_nick_name' in i:
                    vc_person["first_name"] = i['first_nick_name']

                # Handle missing email
                if i["email_1"] is None:
                    vc_person["email"] = ''
                else:
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
                try:
                    ls_customer["personpk"] = str(check_current["Customer"]["Contact"]["custom"])
                except:
                    ls_customer["personpk"] = ""

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
        for i in self.vc.pull("facstaff", parameters=dict(roles='1,2')):
            valid_vc_ids.append(i["person_pk"])
        for i in self.vc.pull("students", parameters=dict(option="2")):
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
        # Warn about debugging
        if self.ui.chk_DebugExport.isChecked():
            self.debug_append_log("Export debugging enabled.", "info")

        # Set current Timezone
        current_store = self.ui.combo_ExportShopSelect.currentText()
        shop_timezone_name = self.ls_shops[current_store]["timeZone"]
        timezone = pytz.timezone(shop_timezone_name)
        shop_timezone_utc_offset = datetime.datetime.now(timezone).strftime('%z')
        shop_timezone_utc_offset_iso = shop_timezone_utc_offset[:3] + ":" + shop_timezone_utc_offset[3:]
        self.debug_append_log(
            "Found %s timezone for shop named %s." % (shop_timezone_name, self.ls_shops[current_store]["name"]),
            "info")

        # Customer Type
        ct = str(self.ui.combo_CustomerType.currentText())
        ct_id = self.ls_customer_types[ct]
        self.debug_append_log("Filtering results to customerType %s, id %s" % (ct, ct_id), "debug")

        # Get selected shop
        shop = str(self.ui.combo_ExportShopSelect.currentText())
        shop_id = self.ls_shops[shop]['shopID']
        self.debug_append_log("Filtering results to shop %s, id %s" % (shop, shop_id), "debug")

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
                                                                                  shop_timezone_utc_offset_iso)
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
            f.append('debug_timestamp')
            f.append('debug_shopID')

        saleline_export_data.append(f)

        for i in salelines['Sale']:
            # Does this invoice have a payment that is on account.
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

                # Verify there are not mixed payments with on credit account
                if isinstance(i['SalePayments']['SalePayment'], list):
                    for p in i['SalePayments']['SalePayment']:
                        if p['PaymentType']['code'] == 'SCA':
                            # Skip sales that mix payments with on_account
                            self.debug_append_log("Skipping Sale #%s (%s %s): Other payments mixed with On Account." %
                                                  (str(i['saleID']),
                                                   str(i['Customer']['firstName']),
                                                   str(i['Customer']['lastName'])),
                                                  "info")
                            continue

                # Depending on how many items sold,
                # types of salelines are returned.
                # List of dictionaries and a single dictionary.
                if isinstance(i['SaleLines']['SaleLine'], list):

                    for s in i['SaleLines']['SaleLine']:

                        # Ignore this entry if it was not in the shop selected.
                        try:
                            if s['shopID'] != shop_id:
                                self.debug_append_log("ShopID for entry is not the shop that was requested, "
                                                      "skipping entry: %s" % str(s), "debug")
                                continue
                        except:
                            self.debug_append_log("Unable to determine shopID for entry: %s." % s, "debug")
                            continue

                        # Format the entry to be added to our export file.
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
                                saleline_single.append(str(i['shopID']))

                            saleline_export_data.append(saleline_single)
                        except:
                            self.debug_append_log("Unable to append item %s for Sale %s data to CSV." %
                                                  (str(s['saleLineID']), str(i['saleID'])), "info")
                            self.debug_append_log("Debug Output: " + str(s), "debug")
                else:
                    try:
                        if 'Item' in i["SaleLines"]["SaleLine"]:
                            # Ignore this entry if it was not in the shop selected.
                            if i["SaleLines"]["SaleLine"]["shopID"] != shop_id:
                                self.debug_append_log("ShopID for entry is not the shop that was requested, "
                                                      "skipping entry: %s" % str(i["SaleLines"]["SaleLine"]),
                                                      "debug")
                                continue
                            # Format the entry to be added to our export file.
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
                                saleline_single.append(str(i["SaleLines"]["SaleLine"]['shopID']))

                            saleline_export_data.append(saleline_single)
                    except:
                        self.debug_append_log("Unable to append single saleline for sale # " + str(i['saleID']),
                                              "info")
                        self.debug_append_log("Debug Output: " + str(i["SaleLines"]["SaleLine"]), "debug")

        try:
            filename = str(self.ui.line_ExportFolder.text())
            filename = filename + '/lightspeed_salelines_export_' + \
                       str(ct) + \
                       "_" + \
                       datetime.datetime.now().strftime('%s') + '.csv'

            with open(filename, 'w') as file:
                writer = csv.writer(file)
                for row in saleline_export_data:
                    writer.writerow(row)
        except:
            self.debug_append_log("Failed to format CSV SaleLine data.", "info")
            self.debug_append_log(sys.exc_info()[0], "debug")
            return None

        # !! Account Balance Export !!
        try:
            # Get Customers with Balance on account. Used to export balances and clear accounts.
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
                            selected_emp = self.ui.combo_ClearChargesEmployee.currentText()
                            emp_id = selected_emp.split("ID:", 1)[1]
                            # Clear the balance for this account
                            self.clear_account_balances(int(i['customerID']),
                                                        float(i['CreditAccount']['balance']),
                                                        int(pt_id),
                                                        int(i["creditAccountID"]),
                                                        int(emp_id))

        except:
            self.debug_append_log("Failed to format CreditBalance Export data.", "info")
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

    def clear_account_balances(self, customerID, balance, paymentID, creditAccountID, emp_id):
        try:
            formatted_request = {
                                "employeeID": emp_id,
                                "registerID": 1,
                                "shopID": 1,
                                "customerID": customerID,
                                "completed": 'true',
                                "SaleLines": {
                                    "SaleLine": {
                                        "itemID": 0,
                                        "note": "Balance Cleared by LSVCConnector",
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
            self.debug_append_log(formatted_request, "debug")

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

    def get_shops(self):
        try:
            shop = self.ls.get("Shop")
            if isinstance(shop['Shop'], list):
                for s in shop['Shop']:
                    self.ls_shops[s["name"]] = s
            else:
                self.ls_shops[shop["Shop"]["name"]] = shop['Shop']
        except:
            self.debug_append_log("Error getting shop names.", "info")

        # Update Shops in UI
        try:
            self.ui.combo_ExportShopSelect.clear()
            self.ui.combo_ExportShopSelect.addItems(self.ls_shops.keys())
        except:
            self.debug_append_log("Error adding shops to UI.", "info")
            self.debug_append_log(str(self.ls_shops), "debug")

    def get_employees(self):
        try:
            emp = self.ls.get("Employee")
            if isinstance(emp['Employee'], list):
                for s in emp['Employee']:
                    name = s["firstName"] + " " + s["lastName"] + " ID:" + s["employeeID"]
                    self.ls_employee[name] = s
            else:
                name = emp["Shop"]["firstName"] + " " + emp["Shop"]["lastName"] + " ID:" + emp["Shop"]["employeeID"]
                self.ls_employee[name] = emp['Employee']
        except:
            self.debug_append_log("Error getting employees from LS.", "info")

        # Update Shops in UI
        try:
            self.ui.combo_ClearChargesEmployee.clear()
            self.ui.combo_ClearChargesEmployee.addItems(self.ls_employee.keys())
        except:
            self.debug_append_log("Error adding employees to UI.", "info")
            self.debug_append_log(str(self.ls_employee), "debug")

    def authorize_app(self):
        """
        Authorize App
        :return:
        """
        try:
            if len(self.c["client_id"]) > 0:
                self.auth_url = "https://cloud.lightspeedapp.com/oauth/authorize.php?" \
                                                 "response_type=code&client_id={}&scope=employee:all".format(self.c["client_id"])
                self.authorize_window = AuthorizeLS(self.auth_url)
                self.authorize_window.interceptor.code_returned.connect(self.authorization_complete)
        except:
            QMessageBox.question(self, 'Authorization Failed',
                                 "Make sure Lightspeed developer client id, secret, and account number has been saved.",
                                 QMessageBox.Ok)

    @pyqtSlot()
    def authorization_complete(self):
        code = self.authorize_window.interceptor.code
        self.authorize_window.view.hide()
        self.debug_append_log('Authorization Code Returned: ' + code, "info")

        if len(code) > 0:
             token = self.ls.get_authorization_token(code)
             self.debug_append_log('Refresh Token Returned: ' + token, "info")
             self.ui.txt_RefreshToken.setText(token)
             QMessageBox.question(self, 'Application Authorized with Lightspeed',
                                  "Application is now authorized with your Lightspeed account. "
                                  "Please restart application.",
                                  QMessageBox.Ok)
             self.save_settings_button()

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
        try:
            if os.path.isdir(log_dir):
                filepath = open(filename, 'w')
                with filepath:
                    filepath.write(self.ui.txtb_SyncLog.toPlainText())
        except:
            self.debug_append_log("Unable to save log file.", "info")

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

        if self.ui.chk_DebugExport.isChecked():
            settings.update({"debug_export": True})
        else:
            settings.update({"debug_export": False})

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
            file = os.path.join(self.working_dir, "LICENSE")
            r = open(file, "r")
            self.ui.textBrowser_License.setText(r.read())
        except:
            self.ui.textBrowser_License.setText("Unable to read license file.")

    def reveal_hidden(self):
        self.debug_append_log("Revealing hidden settings!", "info")
        self.ui.txt_RefreshToken.setEchoMode(QLineEdit.Normal)
        self.ui.txt_DevelSecret.setEchoMode(QLineEdit.Normal)
        self.ui.txt_LSDevelID.setEchoMode(QLineEdit.Normal)
        self.ui.txt_VCUser.setEchoMode(QLineEdit.Normal)
        self.ui.txt_VCPass.setEchoMode(QLineEdit.Normal)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Main()
    window.show()
    sys.exit(app.exec_())