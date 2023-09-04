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
import pandas
from decimal import Decimal, ROUND_HALF_UP
import images
import logging
import traceback
import update
import json

# Set Scaling for High Resolution Displays
if hasattr(Qt, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# Setup Logfile
logfile = os.environ['TEMP'] + "\\LSVCConnectorLog-" + str(datetime.date.today()) +".txt"
logging.basicConfig(filename=logfile)
logging.basicConfig(level=logging.DEBUG)


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
    def __init__(self, auth_url: object) -> object:
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
                              "window,info")

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

        # Initialize Veracross and Lightspeed connection
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
        self.ui.btn_OpenLog.clicked.connect(self.open_log_to_file)

        # Settings Buttons
        self.ui.btn_SaveSettings.clicked.connect(self.save_settings_button)
        self.ui.btn_ExportSettings.clicked.connect(self.export_settings)
        self.ui.btn_ImportSettings.clicked.connect(self.import_settings)

        # Export Tab
        self.ui.chk_ClearCharges.setChecked(False)

        # Export Options Buttons
        self.ui.btn_SaveExportOptions.clicked.connect(self.save_settings_button)

        # Import Options Buttons
        self.ui.btn_SaveImportOptions.clicked.connect(self.save_settings_button)

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

        # Progress bar zero at start
        self.ui.progressBar.setValue(0)

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
        if "import_options_creditamount" in self.c.keys():
            self.ui.spinBox_CreditAmount.setValue(self.c["import_options_creditamount"])
        if "import_options_lastsync" in self.c.keys():
            self.ui.line_LastSyncField.setText(self.c["import_options_lastsync"])
        if "import_options_veracrossid" in self.c.keys():
            self.ui.line_VeracrossIDField.setText(self.c["import_options_veracrossid"])

        # Store data
        self.export_dir = ""
        self.ls_customer_types = dict()
        self.ls_payment_types = dict()
        self.ls_shops = dict()
        self.ls_employee = dict()

        # Get some initial LS Data
        self.get_customer_types()
        self.get_payment_types()
        self.get_CustomField()
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
                self.debug_append_log("Updated Version Available!", "window,info")
                self.debug_append_log("Latest Description:", "info,window")
                self.debug_append_log(self.version.latest_description(), "window,info")
                self.debug_append_log("Download at "
                                      "https://github.com/beckf/lightspeed-vc-connector/releases/latest", "window,info")
        except:
            self.debug_append_log("Error checking for updates.", "window,debug")

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
        self.debug_append_log("User Sync Complete.", "window,info")

    def create_update_customer(self):

        param = {}
        # Make sure we have a lastsync and veracross id field mapped.
        if self.veracrossid_field is None or self.lastsync_field is None:
            self.debug_append_log("Enter valid map fields for VeracrossID and LastSync first.", "window,info")
            return None

        # Determine if we are syncing VC changes after particular date and update params set to VC.
        if self.ui.checkBox_SyncChangesAfterDate.isChecked():
            updated_after_ui = self.ui.dateEdit_SyncUpdatedAfterDate.date()
            param.update({"updated_after": str(updated_after_ui.toPyDate())})

        # If we are working with students, add additional parameters.
        if self.ui.combo_SyncVCUserType.currentText() == "Students":
            self.debug_append_log("Getting Veracross Students (Current)", "window,info")

            # Add a grade level filter
            if not self.ui.combo_SyncGradeLevel.currentText() == "None":
                if "Other" in self.ui.combo_SyncGradeLevel.currentText():
                    # Append non-standard grades to the grade_level param. 20-30
                    param.update({"grade_level": ",".join(str(x) for x in list(range(20, 30)))})
                else:
                    param.update({"grade_level": self.ui.combo_SyncGradeLevel.currentText()})

            # Limit to only current students
            param.update({"option": "2"})

            # Show our parameters to debug log
            self.debug_append_log("VC Parameters: " + str(param), "debug")

            # Get Veracross data for students
            vcdata = self.vc.pull("students", parameters=param)

            # Get Lightspeed id number that matches customer_type Student
            try:
                ls_customerTypeID = self.ls_customer_types["Student"]
            except:
                self.debug_append_log("Unable to get CustomerType of Student from Lightspeed. "
                                      "Check name of CustomerType in Lightspeed.", "window,info")

        # Determine if we want FacultyStaff from VC
        elif self.ui.combo_SyncVCUserType.currentText() == "Faculty Staff":
            # Let user know whats up
            self.debug_append_log("Getting Veracross Faculty Staff (Faculty and Staff)", "window,info")
            # Limit to roles 1 & 2 in VC Api.
            param.update({"roles": "1,2"})

            # Show parameters to debug log
            self.debug_append_log("VC Parameters: " + str(param), "debug")

            # Get Veracross data for Faculty Staff
            vcdata = self.vc.pull("facstaff", parameters=param)

            # Determine what Lightspeed customer id number for FacStaff
            try:
                ls_customerTypeID = self.ls_customer_types["FacultyStaff"]
            except:
                self.debug_append_log("Unable to get CustomerType of FacultyStaff from Lightspeed. "
                                      "Check name of CustomerType in Lightspeed.", "window,info")

        # User did not select a user type
        else:
            self.debug_append_log("Select Veracross User Type first.", "window,info")
            return None

        # Going to use progress bar.  Make sure it is at zero first.
        self.ui.progressBar.setValue(0)

        # Determine each increment for progress bar.
        increment = 100 / len(vcdata)
        total_increment = 0

        # Loop through the data from VC.
        for i in vcdata:

            # increment the progress bar.
            total_increment = total_increment + increment
            self.ui.progressBar.setValue(int(total_increment))

            self.debug_append_log("Processing VC Record {}".format(i["person_pk"]), "debug")

            # Get household data for this person
            hh = self.vc.pull("households/" + str(i["household_fk"]))
            h = hh["household"]

            # Set search parameters for lightspeed and see if we find someone in LS.
            lsparam = dict(load_relations='all', limit=1, companyRegistrationNumber=str(i["person_pk"]))
            check_current = self.ls.get("Customer", parameters=lsparam)

            # Format data to how it should look. First name will format later.
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
                                     'creditLimit': str(self.c["import_options_creditamount"]) + '.00'
                                 },
                                 'CustomFieldValues': {
                                     'CustomFieldValue': [{
                                         'customFieldID': self.veracrossid_field,
                                         'value': i["person_pk"]
                                     }, {
                                         'customFieldID': self.lastsync_field,
                                         'value': str(datetime.datetime.now())
                                     }
                                     ]}
                                 }
                            }

            # Update data to use correct nick name format from VC.
            # Added becuase of bug in VC API where sometimes one is returned over other.
            if 'nick_first_name' in i:
                vc_formatted['Customer']['firstName'] = i['nick_first_name']
            elif 'first_nick_name' in i:
                vc_formatted['Customer']['firstName'] = i['first_nick_name']

            # Did we find a record in lightspeed to sync to?
            if check_current:

                # Create two dictionaries one for VC and the other for LS
                # We will see if they match later.
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

                # Compare the data. Are the two dictionaries the same...
                if not ls_customer == vc_person or self.ui.checkBox_ForceSync.isChecked():
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
                self.debug_append_log("Adding new Lightspeed Customer for {} {}".format(
                    vc_formatted['Customer']['firstName'],
                    vc_formatted['Customer']['lastName']),
                    "info")
                try:
                    new_customer = self.ls.create("Customer", vc_formatted["Customer"])
                    self.debug_append_log(
                        "New Customer # {} Added: {} {}".format(new_customer['Customer']['customerID'],
                                                                new_customer['Customer']['firstName'],
                                                                new_customer['Customer']['lastName']),
                        "info")
                except:
                    self.debug_append_log("Unable to add new Lightspeed Customer for {} {}".format(
                        vc_formatted['Customer']['firstName'],
                        vc_formatted['Customer']['lastName']),
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
        self.debug_append_log("Inactive user delete complete.", "window,info")

    def delete_customer(self):
        """
        Delete records in Lightspeed.  Filters customers to those that have a companyRegistrationNumber
        :return:
        """
        self.debug_append_log("Checking for customers to delete.", "window,info")

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
        self.debug_append_log("File export complete.", "window,info")

    def export_charge_balance(self):
        """
        Export Charges from LS in CSV
        :return:
        """
        # Warn about debugging
        if self.ui.chk_DebugExport.isChecked():
            self.debug_append_log("Export debugging enabled.", "window,info")

        # Set current Timezone
        current_store = self.ui.combo_ExportShopSelect.currentText()
        shop_timezone_name = self.ls_shops[current_store]["timeZone"]
        timezone = pytz.timezone(shop_timezone_name)
        shop_timezone_utc_offset = datetime.datetime.now(timezone).strftime('%z')
        shop_timezone_utc_offset_iso = shop_timezone_utc_offset[:3] + ":" + shop_timezone_utc_offset[3:]
        self.debug_append_log(
            "Found %s timezone for shop named %s." % (shop_timezone_name, self.ls_shops[current_store]["name"]),
            "window,info")

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
            self.debug_append_log("Missing export folder location.", "window,info")
            self.select_export_directory()

        # Notify UI
        self.debug_append_log("Export started for customer type: " + str(ct), "window,info")

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

        # Determine each increment for progress bar.
        increment = 100 / len(salelines['Sale'])
        total_increment = 0

        for i in salelines['Sale']:

            # increment the progress bar.
            total_increment = total_increment + increment
            self.ui.progressBar.setValue(int(total_increment))

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
                # Is this multiline sale?
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

                        # Determine correct item description to use:
                        try:
                            if 'Item' in s:
                                if 'description' in s['Item']:
                                    description = str(s['Item']['description'])
                                else:
                                    description = "Unknown"
                            elif 'Note' in s:
                                if 'note' in s['Note']:
                                    description = str(s['Note']['note'])
                                    self.debug_append_log("Debug Output: Sale line without actual item: " +
                                                          str(description), "debug")
                            else:
                                description = "Unknown"
                        except:
                            description = "Unknown"

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
                                               str(description),
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
                            self.debug_append_log("Unable to append item (multisale) %s for Sale %s data to CSV." %
                                                  (str(s['saleLineID']), str(i['saleID'])), "info")
                            self.debug_append_log("Debug Output: " + str(s), "debug")
                else:
                    try:
                        # Is this a singleline sale?
                        if 'Item' in i["SaleLines"]["SaleLine"]:
                        # Need to be able to identify the item by it's type and not if it has items.
                        # What if only single misc charge?  To do this the way we clear balances needs to be change.
                        # Ideally we would want a Payment to CC Account.
                        #if isinstance(i["SaleLines"]["SaleLine"], dict):
                            # Ignore this entry if it was not in the shop selected.
                            if i["SaleLines"]["SaleLine"]["shopID"] != shop_id:
                                self.debug_append_log("ShopID for entry is not the shop that was requested, "
                                                      "skipping entry: %s" % str(i["SaleLines"]["SaleLine"]),
                                                      "debug")
                                continue

                            # Determine a description
                            try:
                                if 'Item' in i["SaleLines"]["SaleLine"]:
                                    if 'description' in i["SaleLines"]["SaleLine"]['Item']:
                                        description = str(i["SaleLines"]["SaleLine"]['Item']['description'])
                                    else:
                                        description = "Unknown"
                                elif 'Note' in i["SaleLines"]["SaleLine"]:
                                    if 'note' in i["SaleLines"]["SaleLine"]['Note']:
                                        description = str(i["SaleLines"]["SaleLine"]['Note']['note'])
                                        self.debug_append_log("Debug Output: Sale line without actual item: " +
                                                              str(description), "debug")
                                else:
                                    description = "Unknown"
                            except:
                                description = "Unknown"

                            # Format the entry to be added to our export file.
                            saleline_single = [str(i['Customer']['companyRegistrationNumber']),
                                               str(i['Customer']['companyRegistrationNumber']),
                                               str(i['Customer']['firstName'] + " " + i['Customer']['lastName']),
                                               self.ui.txt_ExportOptionsTransactionSource.text(),
                                               self.ui.txt_ExportOptionsTransactionType.text(),
                                               self.ui.txt_ExportOptionsSchoolYear.text(),
                                               str(i["SaleLines"]["SaleLine"]['timeStamp'][:10]),
                                               self.ui.txt_ExportOptionsCatalog_Item_fk.text(),
                                               str(description),
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
                        self.debug_append_log("Unable to append (single) saleline for sale # " + str(i['saleID']),
                                              "info")
                        self.debug_append_log("Debug Output: " + str(i["SaleLines"]["SaleLine"]), "debug")

        try:
            filename = str(self.ui.line_ExportFolder.text())
            filename = filename + '/lightspeed_salelines_export_' + \
                       datetime.datetime.now().strftime('%m%d%Y-%H%m%S') + '.xlsx'
            self.debug_append_log(str(filename), "info")
        except:
            self.debug_append_log("Unable to determine export file.", "window,info")

        try:
            writer = pandas.ExcelWriter(filename, engine='xlsxwriter')
            panda_data = pandas.DataFrame(saleline_export_data)
            panda_data.to_excel(writer, sheet_name='Sheet1', header=False, index=False)
            writer.save()
        except:
            self.debug_append_log("Failed to format XLSX SaleLine data.", "window,info")
            return None

        # !! Account Balance Export !!
        try:
            # Get Customers with Balance on account. Used to export balances and clear accounts.
            customers = self.ls.get("Customer", parameters=dict(load_relations='["CreditAccount"]'))
        except:
            self.debug_append_log("Unable to get Customer data from Lightspeed.", "window,info")
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
                       datetime.datetime.now().strftime('%m%d%Y-%H%m%S') + '.xlsx'

            writer = pandas.ExcelWriter(filename, engine='xlsxwriter')
            panda_data = pandas.DataFrame(export_data)
            panda_data.to_excel(writer, sheet_name='Sheet1', header=False, index=False)
            writer.save()
        except:
            self.debug_append_log("Failed to export XLSX balance data.", "window,info")
            return None

        # Finish of progress bar
        self.ui.progressBar.setValue(int(100))

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
            self.debug_append_log("Unable to format data to clear balances.", "window,info")

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
            self.debug_append_log("Cannot get customer types from API, or none exist.", "window,info")
        # Update UI
        try:
            self.ui.combo_CustomerType.clear()
            self.ui.combo_CustomerType.addItems(self.ls_customer_types.keys())
        except:
            self.debug_append_log("Error getting customer types.", "window,info")

    def get_payment_types(self):
        try:
            pt = self.ls.get("PaymentType")
            for i in pt['PaymentType']:
                self.ls_payment_types[i["name"]] = i["paymentTypeID"]
        except:
            self.debug_append_log("Cannot get payment types from API.", "window,info")

        # Update UI
        try:
            self.ui.combo_PaymentType.clear()
            self.ui.combo_PaymentType.addItems(self.ls_payment_types.keys())
        except:
            self.debug_append_log("Error getting payment types.", "window,info")

        try:
            self.ui.combo_PaymentType.setCurrentIndex(self.ui.combo_PaymentType.findText("Credit Account"))
        except:
            self.debug_append_log("Unable to set default payment type to Credit Account.", "window,info")

    def get_CustomField(self):
        """
        Get the Lightspeed id for the customfields
        :return:
        """
        self.veracrossid_field = None
        self.lastsync_field = None

        try:
            custom_fields = self.ls.get("Customer/CustomField")
            if isinstance(custom_fields["CustomField"], list):
                for cf in custom_fields["CustomField"]:
                    # Find internal id for VeracrossID Field
                    if str(cf["name"]) == str(self.ui.line_VeracrossIDField.text()):
                        self.veracrossid_field = cf["customFieldID"]

                    # Find internal id for LastSync Field
                    if str(cf["name"]) == str(self.ui.line_LastSyncField.text()):
                        self.lastsync_field = cf["customFieldID"]

        except:
            self.debug_append_log("Something went wrong when trying to match custom import fields!", "debug")

        if self.veracrossid_field is None:
            self.debug_append_log("Unable to find Lightspeed custom import field for VeracrossID.", "window,info")
        if self.lastsync_field is None:
            self.debug_append_log("Unable to find Lightspeed custom import field for LastSync.", "window,info")

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
            self.debug_append_log("Error adding shops to UI.", "window,info")
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
            self.debug_append_log("Error getting employees from LS.", "window,info")

        # Update Shops in UI
        try:
            self.ui.combo_ClearChargesEmployee.clear()
            self.ui.combo_ClearChargesEmployee.addItems(self.ls_employee.keys())
        except:
            self.debug_append_log("Error adding employees to UI.", "window,info")
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
        self.debug_append_log('Authorization Code Returned: ' + code, "window,info")

        if len(code) > 0:
             token = self.ls.get_authorization_token(code)
             self.debug_append_log('Refresh Token Returned: ' + token, "window,info")
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
        try:
            if "window" in level:
                self.ui.txtb_SyncLog.append(text)
        except:
            traceback.print_exc()
        try:
            if "debug" in level and self.ui.chk_DebugExport.isChecked():
                logging.warning(text)
        except:
            traceback.print_exc()
        try:
            if "info" in level:
                logging.warning(text)
        except:
            traceback.print_exc()

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

    def open_log_to_file(self):
        filename = os.environ['TEMP'] + "\\LSVCConnectorLog-" + str(datetime.date.today()) +".txt"
        try:
            if os.path.isfile(filename):
                os.startfile(filename)
        except:
            self.debug_append_log("Unable to open log file.", "window,info")

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
            "vc_export_transaction_source": self.ui.txt_ExportOptionsTransactionSource.text(),
            "import_options_creditamount": self.ui.spinBox_CreditAmount.value(),
            "import_options_lastsync": self.ui.line_LastSyncField.text(),
            "import_options_veracrossid": self.ui.line_VeracrossIDField.text()
        }

        if self.ui.chk_DebugExport.isChecked():
            settings.update({"debug_export": True})
        else:
            settings.update({"debug_export": False})

        # Save settings
        config.save_settings(settings, "config", self.config_passwd)
        # Reload Settings
        self.c = config.load_settings("config", self.config_passwd)
        self.get_CustomField()

        # Suggest user restart the app
        QMessageBox.question(self, 'Settings Saved',
                             "The settings have been saved",
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
        self.debug_append_log("Revealing hidden settings!", "window,info")
        self.ui.txt_RefreshToken.setEchoMode(QLineEdit.Normal)
        self.ui.txt_DevelSecret.setEchoMode(QLineEdit.Normal)
        self.ui.txt_LSDevelID.setEchoMode(QLineEdit.Normal)
        self.ui.txt_VCUser.setEchoMode(QLineEdit.Normal)
        self.ui.txt_VCPass.setEchoMode(QLineEdit.Normal)

    def export_settings(self):
        export_dir = QFileDialog.getExistingDirectory(self, 'Select directory to save settings to.')
        with open(export_dir + "/config.json", "w") as outfile:
            json.dump(self.c, outfile, indent=4)

    def import_settings(self):
        QMessageBox.question(self, 'Importing Settings',
                             "Select Import File. Once imported, application will save and quit.",
                             QMessageBox.Ok)
        import_file = QFileDialog.getOpenFileName(self, 'Select json config file to import.')
        if os.path.isfile(import_file[0]):
            with open(import_file[0], "r") as infile:
                import_json = json.load(infile)
                config.save_settings(import_json, "config", self.config_passwd)
                # Reload Settings
                self.c = config.load_settings("config", self.config_passwd)
                self.close()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Main()
    window.show()
    sys.exit(app.exec_())