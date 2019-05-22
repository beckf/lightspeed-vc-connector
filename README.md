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
* Export of individual SaleLines as opposed to the entire invoice total will round the totals differently from LS.  

### Screenshots
![alt text](images/sync.png "Sync Tab")

![alt text](images/export.png "Export Tab")

![alt text](images/export_options.png "Export Options Tab")

![alt text](images/settings.png "Settings Tab")

![alt text](images/password_tab.png "Password Tab")

![alt text](images/authorize.png "Authorize Tab")


### How to Get Started
1) Create two CustomerTypes in your Lightspeed shop. **Student** and **FacultyStaff**

2) [Signup with Lightspeed OAuth](https://cloud.lightspeedapp.com/oauth/register.php)

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

7) Go to the Authorize Tab and click the Authorize link.  Login to LS using your admin login id and password.

8) Grant your application access to the account.  When granted, if you used localhost as the redirect, you will see an error not found page.  
In the URL copy the token after the equals sign and paste this into the first text box. You must complete the next step within 30 seconds.  

9) Click Authorize.

10) Copy and paste the returned Refresh Token from the Authorize Tab to the settings tab on the LS Refresh Token field.

11) Click Save settings.