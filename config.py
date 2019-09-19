import sys
import os
import shelve
import pyAesCrypt

default_config = dict()

if sys.platform == "darwin":
    # OS X
    config_file = os.environ['HOME'] + '/Library/Preferences/lightspeed-vc-connector-prefs'
    config_file_extension = ".db"
    if not os.path.isfile(config_file + config_file_extension):
        d = shelve.open(config_file, flag='c', writeback=True)
        d["config"] = default_config
        d.sync()
        d.close()

elif "win" in sys.platform:
    # Windows
    config_file = os.environ['LOCALAPPDATA'] + "\lightspeed-vc-connector-prefs"
    config_file_extension = ".dat"
    if not os.path.isfile(config_file + config_file_extension):
        d = shelve.open(config_file, flag='c', writeback=True)
        d["config"] = default_config
        d.sync()
        d.close()

else:
    config_file = "lightspeed-vc-connector-prefs"
    if not os.path.isfile(config_file):
        d = shelve.open(config_file, flag='c', writeback=True)
        d["config"] = default_config
        d.sync()
        d.close()

config_file_enc = config_file + ".aes"


def check_enc():
    """
    Check that encrypted settings are present
    :return: True/False
    """
    if os.path.isfile(config_file + ".aes"):
        return True
    else:
        return False


def encrypt(password):
    """
    Encrypt settings
    :param password:
    :return:
    """
    if not check_enc():
        buffersize = 64 * 1024
        if os.path.isfile(config_file + config_file_extension):
            pyAesCrypt.encryptFile(config_file + config_file_extension, config_file_enc, password, buffersize)
            os.remove(config_file + config_file_extension)


def decrypt(password):
    """
    Encrypt settings
    :param password:
    :return:
    """
    if check_enc():
        buffersize = 64 * 1024
        if os.path.isfile(config_file + config_file_extension):
            pyAesCrypt.decryptFile(config_file_enc, config_file + config_file_extension, password, buffersize)
        os.remove(config_file_enc)


def save_settings(settings, key, passwd):
    """
    Saves settings to the pickle file
    :param settings:  data to save.
    :param key: shelve key to save the data to
    :return: nothing
    """
    decrypt(password=passwd)
    d = shelve.open(config_file, flag='c', writeback=True)
    d[key] = settings
    d.sync()
    d.close()
    encrypt(password=passwd)


def load_settings(key, passwd):
    """
    Get settings from pickle file
    :return: data from file
    """
    decrypt(password=passwd)
    d = shelve.open(config_file, flag='c', writeback=True)
    s = d[key]
    d.close()
    encrypt(password=passwd)
    return s


def change_password(old, new):
    """
    Updates encryption password.
    :param old:
    :param new:
    :return:
    """
    decrypt(password=old)
    encrypt(password=new)


def config_file_location():
    return config_file
