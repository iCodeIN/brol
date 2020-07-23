#!/usr/bin/python3

#Hexlify
from binascii import hexlify
#AES
from Crypto.Cipher import AES
#Enums
from enum import Enum
#Getopt
from getopt import getopt, GetoptError
#HMAC
from hashlib import md5 as hash_md5
import hmac
#Argv
from sys import argv, exit

PROGRAM_NAME = "crypter.py"
USAGE = "%s [OPTIONS...] [INPUT_FILE] [OUTPUT_FILE]\n\
    Where options are:\n\
    \t-d\t\t\tDecrypt file\n\
    \t-e\t\t\tEncrypt file\n\
    \t-k\t\t\tKey used to encrypt/decrypt file\n\
    \t-f\t\t\tRead key from file\n\
    \t-v\t\t\tVerbose\n\
    \t-h\t\t\tShow this page\n\
    " % PROGRAM_NAME

KNRM = "\x1B[0m"
KRED = "\x1B[31m"
KGRN = "\x1B[32m"
KYEL = "\x1B[33m"
KBLU = "\x1B[34m"
KMAG = "\x1B[35m"
KCYN = "\x1B[36m"
KWHT = "\x1B[37m"

verbose = False

class CrypterMode(Enum):
    DECRYPT = 0
    ENCRYPT = 1
    UNDEFINED = 2

def print_err(message: str):
    """
    Print error

    :param message: message to print
    :type message: str
    """
    print("%s%s%s" % (KRED, message, KNRM))

def print_info(message: str):
    """
    Print information.
    The message will be displayed only when set in verbose mode

    :param message: message to print
    :type message: str
    """
    global verbose
    if verbose:
        print("%s%s%s" % (KYEL, message, KNRM))

def usage(err: str = None):
    """
    Print usage
    """
    if err:
        print_err(err)
    print("%s" % USAGE)

def encrypt_file(input_file: str, output_file: str, crypter_key: str) -> bool:
    """
    Encrypt a file using AES/HMAC MD5 using the provided Key

    :param input_file: file to encrypt
    :param output_file: where to write the encrypted file content
    :param crypter_key: key to use to encrypt data
    :type input_file: str
    :type output_file: str
    :type crypter_key: str
    :returns bool
    """
    #Crypter key to bytes
    crypter_key = crypter_key.encode()
    try:
        ihnd = open(input_file, 'rb')
        #Get file size
        ihnd.seek(0, 2)
        filesize = ihnd.tell()
        ihnd.seek(0, 0)
        filesize_bytes = bytearray()
        filesize_bytes.append(filesize & 0xff)
        filesize_bytes.append((filesize << 8) & 0xff)
        filesize_bytes.append((filesize << 16) & 0xff)
        filesize_bytes.append((filesize << 24) & 0xff)
        digest = hash_md5()
        digest.update(filesize_bytes)
        iv = bytearray(digest.digest())
        #Iv[15] must be AND with 0xF0 and then OR with filesize & 0x0F
        iv[15] = (iv[15] & 0xF0) | (filesize & 0x0F)
        #Write filename at the beginning of file
        print_info("IV is %s" % hexlify(iv))
        #AES key is MD5SUM between IV and crypter key
        digest = hash_md5()
        digest.update(iv)
        digest.update(crypter_key)
        aes_key = digest.digest()
        print_info("AES key is %s" % hexlify(aes_key))
        #Init AES crypter
        crypter = AES.new(aes_key, AES.MODE_CBC, bytearray(iv))
        #Prepare key_ipad and k_opad, I don't know what they are...
        key_opad = bytearray()
        key_ipad = bytearray()
        for i in range(64):
            key_ipad.append(0x36)
            key_opad.append(0x5C)
        for i in range(16):
            key_ipad[i] = 0x36 ^ aes_key[i]
            key_opad[i] = 0x5C ^ aes_key[i]
        #Prepare the final digest
        digest = hash_md5()
        digest.update(key_ipad)
        #Open file
        try:
            ohnd = open(output_file, 'wb')
            #Write IV
            ohnd.write(iv)
            #Read, Encrypt and write
            index = 0
            input_block = bytearray(16)
            while index < filesize:
                size = 16
                if filesize - index < 16:
                    size = filesize - index
                for i in range(size):
                    input_block[i] = ord(ihnd.read(1))
                input_block = bytearray(crypter.encrypt(bytes(input_block)))
                #Write bytes
                ohnd.write(input_block)
                #Update digest with encrypted block
                digest.update(input_block)
                index += size
            #Calculate final HMAC
            final_hmac = digest.digest()
            digest = hash_md5()
            digest.update(key_opad)
            digest.update(final_hmac)
            final_hmac = digest.digest()
            print_info("HMAC: %s" % hexlify(final_hmac))
            #Write HMAC at the end of the file
            ohnd.write(final_hmac)
            print_info("Wrote %d bytes" % (index + 32))
            ohnd.close()
        except IOError as err:
            print_err("IOError: %s" % err)
            return False
        ihnd.close()
    except IOError as err:
        print_err("Could not open input file %s: %s" % (input_file, err))
        return False
    print_info("Encrypted data written to %s" % output_file)
    return True

def decrypt_file(input_file: str, output_file: str, crypter_key: str) -> bool:
    """
    Decrypt a file using AES/HMAC MD5 using the provided Key

    :param input_file: file to decrypt
    :param output_file: where to write the decrypted file content
    :param crypter_key: key to use to decrypt data
    :type input_file: str
    :type output_file: str
    :type crypter_key: str
    :returns bool
    """
    #Crypter key to bytes
    crypter_key = crypter_key.encode()
    try:
        ihnd = open(input_file, 'rb')
        ihnd.seek(0, 2)
        filesize = ihnd.tell()
        if filesize < 32:
            print_err("File is too short to be decrypted")
            return False
        if filesize % 16 != 0:
            print_err("File size must be multiple of 16")
            return False
        ihnd.seek(0, 0)
        #Read first 16 bytes (IV)
        iv = ihnd.read(16)
        lastn = iv[15] & 0x0F
        print_info("IV is %s" % hexlify(iv))
        #AES key is MD5sum between the crypter key and the IV
        digest = hash_md5()
        digest.update(iv)
        digest.update(crypter_key)
        aes_key = digest.digest()
        print_info("AES key is %s" % hexlify(aes_key))
        #Init AES crypter
        crypter = AES.new(aes_key, AES.MODE_CBC, iv)
        #Prepare key_ipad and k_opad, I don't know what they are...
        key_opad = bytearray()
        key_ipad = bytearray()
        for i in range(64):
            key_ipad.append(0x36)
            key_opad.append(0x5C)
        for i in range(16):
            key_ipad[i] = 0x36 ^ aes_key[i]
            key_opad[i] = 0x5C ^ aes_key[i]
        datasize = filesize - 32 #filesize - IV - HMAC
        #Get HMAC
        ihnd.seek(-16, 2) #Last 16 bytes
        final_hmac_in = ihnd.read(16)
        #Verify HMAC before decrypting
        digest = hash_md5()
        digest.update(key_ipad)
        #Return to 16th byte
        ihnd.seek(16, 0)
        #Digest
        while ihnd.tell() <= datasize: # <= cause we're already at 16 (imagine if filesize were 48, datasize would be 16)
            digest.update(ihnd.read(16))
        final_hmac = digest.digest()
        #Opad + md5sum(ipad, file)
        digest = hash_md5()
        digest.update(key_opad)
        digest.update(final_hmac)
        final_hmac = digest.digest()
        #Compare HMAC
        print_info("HMAC from file: %s" % hexlify(final_hmac_in))
        print_info("HMAC calculated: %s" % hexlify(final_hmac))
        if final_hmac != final_hmac_in:
            print_err("HMAC doesn't match")
            return False
        #Return to 16th byte
        ihnd.seek(16, 0)
        #Read and decrypt
        try:
            #Open output file
            ohnd = open(output_file, "wb")
            offset = 0
            while offset < datasize: # <= cause we're already at 16 (imagine if filesize were 48, datasize would be 16)
                input_block = bytearray()
                input_block.extend(ihnd.read(16))
                #Encrypt block and append to encrypted data
                decrypted_block = crypter.decrypt(bytes(input_block))
                #Write decrypted block (only block length)
                offset += 16
                if lastn > 0 and offset == datasize: #Write remaining bytes
                    ohnd.write(decrypted_block[0:lastn])
                else:
                    ohnd.write(decrypted_block) #Write entire block otherwise
            #Close file
            ohnd.close()
        except IOError as err:
            print_err("IOError: %s" % err)
            return False
        print_info("Data decrypted (%d bytes)" % datasize)
        #Close file
        ihnd.close()
    except IOError as err:
        print_err("Could not open input file %s: %s" % (input_file, err))
        return False
    return True

def main(argc: int, argv: list) -> int:
    #Get option
    global verbose
    crypter_mode = CrypterMode.UNDEFINED
    crypter_key = None
    input_file = None
    output_file = None
    try:
        optlist, args = getopt(argv, "edk:f:vh")
        #Iterate over options
        for opt, arg in optlist:
            if opt == "-d":
                crypter_mode = CrypterMode.DECRYPT
            elif opt == "-e":
                crypter_mode = CrypterMode.ENCRYPT
            elif opt == "-k":
                crypter_key = arg
            elif opt == "-f":
                #Read file
                try:
                    hnd = open(arg, "r")
                    crypter_key = hnd.readline()
                    crypter_key = crypter_key.rstrip()
                    hnd.close()
                except IOError as err:
                    print_err("Could not read key from file: %s" % err)
                    return 255
            elif opt == "-v":
                verbose = True
            elif opt == "-h":
                usage()
                return 255
        #Look for database path
        if args:
            if len(args) < 2:
                usage("Missing I/O files")
                return 255
            input_file = args[0]
            output_file = args[1]
        else:
            usage("Missing I/O files")
            return 255
    except GetoptError as err:
        usage(err)
        return 255
    if not crypter_key:
        print_err("Please provide secret key")
        return 1
    #Encrypt/Decrypt file
    if crypter_mode == CrypterMode.ENCRYPT:
        if not encrypt_file(input_file, output_file, crypter_key):
            return 1
    elif crypter_mode == CrypterMode.DECRYPT:
        if not decrypt_file(input_file, output_file, crypter_key):
            return 1
    else:
        print_err("Nothing to do")
        return 255
    return 0

if __name__ == "__main__":
    exit(main(len(argv) - 1, argv[1:]))