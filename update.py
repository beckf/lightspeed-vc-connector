import requests
import os
import sys


class Update:

    def __init__(self):
        self.project_url = 'https://api.github.com/repos/beckf/lightspeed-vc-connector'
        self.current_version = ''

        # Find working directory for VERSION File
        try:
            self.working_dir = sys._MEIPASS
        except AttributeError:
            self.working_dir = os.getcwd()

        # Methods to run now
        self.check_current()

    def check_current(self):
        try:
            file = os.path.join(self.working_dir, "VERSION")
            r = open(file, "r")
            self.current_version = r.read()
        except:
            self.current_version = None

    def update_avail(self):
        """
        Check to see if any updates are available from GitHub
        :return: True/False
        """
        try:
            r = requests.get(self.project_url + '/releases/latest')

            if r.status_code == 200:
                d = r.json()
                if self.current_version == d['tag_name'].rsplit('v', 2)[1]:
                    return False
                else:
                    return True
            return False
        except:
            return False


