# Veracross and Lightspeed HQ POS Sync Connector

This is a PyQT application developed to provide integration between Veracross and Lightspeed.

### Features
* Settings are encrypted in AES256-CBC.
* Create and update customers in Lightspeed directly from Veracross API.
* Create and update customers that have been updated in VC after a specific date.
* Create and update customers based on Veracross Grade Level.
* Delete customers that are no longer in Veracross and do not have a credit balance.
* Export charges from Lightspeed in a CSV format that is usable by VC.
* Export charges by individual sale items, or credit balance total.
* Clear charge accounts back to zero by applying an exact credit after exporting.
* Easily authorize the application using your own Lightspeed Developer account and your Lightspeed Retail account.

### Known Issues
* Export of individual SaleLines as opposed to the entire invoice total will round the totals differently. 
SaleLines are stored in Lightspeed to the thousandth of a cent.  This means that the invoice total could be rounded 
differently than each individual item.

### Screenshots
![alt text](images/sync.png "Sync Tab")

![alt text](images/export.png "Export Tab")

![alt text](images/export_options.png "Export Options Tab")

![alt text](images/settings.png "Settings Tab")

![alt text](images/password_tab.png "Password Tab")

![alt text](images/authorize.png "Authorize Tab")


### How to Get Started
1) Create two CustomerTypes in your Lightspeed shop for Veracross Students and Faculty named **Student** and **FacultyStaff**

2) [Signup with Lightspeed OAuth](https://cloud.lightspeedapp.com/oauth/register.php).
* You will run the application under your own Lightspeed developer account/application.
* Be sure to set the redirect URI to http://localhost . This will leave the refresh token in the browser window for you 
to copy/paste in step 10. You will copy/paste the key show after the equals sign in the URL.

![alt text](images/ls_oauth_signup.png "LS OAuth")

3) Obtain Veracross API credentials from VC Account Rep.
    
4) Run the application.  You will be prompted for a password.  This password will be used for encrypting the settings file.

5) On the settings tab, enter:
* LS Account ID Number (Click Username when logged into Lightspeed)
* LS Developer Client Developer ID
* LS Developer Client Secret
* VC Username
* VC Password

6) Click Save Settings and restart the application.

7) Go to the Authorize Tab and click the Authorize Button.  Login to LS using your admin login id and password.

8) Grant your application access to the account. 

10) Restart the application.