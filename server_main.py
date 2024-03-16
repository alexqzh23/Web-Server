import sys
import logging
import time
import psutil
import threading
import socket
import mysql.connector
import server_tool

from PyQt6.QtWidgets import (
    QMainWindow, QApplication, QPushButton,
    QLabel, QWidget, QTextEdit, QLineEdit,
    QHBoxLayout, QVBoxLayout
)
from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QThread, QObject

# Log configuration
logging.basicConfig(filename='./server.log', filemode='a', level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def get_host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
        return ip


class MonitorWorker(QObject):
    cpu_signals = QtCore.pyqtSignal(float)
    ram_signals = QtCore.pyqtSignal(float)

    @QtCore.pyqtSlot(bool)
    def run_cpu_usage(self):
        cpu_usage = psutil.cpu_percent(1)
        self.cpu_signals.emit(cpu_usage)

    @QtCore.pyqtSlot(bool)
    def run_ram_usage(self):
        ram_usage = psutil.virtual_memory()[2]
        self.ram_signals.emit(ram_usage)


# To package information of connection
class ConnectionInfo:
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr

    def get_sock(self):
        return self.sock

    def get_addr(self):
        return self.addr


# a Thread to wait the connection of new clients
class Receptionist(QObject):
    connection_signal = QtCore.pyqtSignal(ConnectionInfo)

    def __init__(self, sock):
        super(Receptionist, self).__init__()

        self.sock = sock

    @QtCore.pyqtSlot(bool)
    def working(self):
        # print('I am working')
        sock, addr = self.sock.accept()
        connection_info = ConnectionInfo(sock, addr)
        self.connection_signal.emit(connection_info)


# Server Object
class Server(QObject):
    addr_text_signal = QtCore.pyqtSignal(tuple)  # addr info
    receptionist_working_signal = QtCore.pyqtSignal(bool)  # signal to let the receptionist working

    def __init__(self, ip, port):
        super(Server, self).__init__()

        self.open = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((ip, port))
        self.sock.listen(10)
        self.response_headers = "HTTP/1.1 200 OK\r\n"
        self.response_headers += "\r\n"

        # Initialize receptionist
        self.receptionist = Receptionist(self.sock)
        self.receptionist.connection_signal.connect(self.recept_client)
        # Link working order to receptionist
        self.receptionist_working_signal.connect(self.receptionist.working)
        # Add to a new Thread
        self.receptionist_thread = QThread()
        self.receptionist.moveToThread(self.receptionist_thread)

    @QtCore.pyqtSlot(bool)
    def start(self):
        self.open = True
        self.receptionist_thread.start()  # start thread
        self.receptionist_working_signal.emit(True)
        print("Server start!")

    @QtCore.pyqtSlot(ConnectionInfo)
    def recept_client(self, signal):
        sock = signal.get_sock()
        addr = signal.get_addr()
        # Run the tcp lick
        thread = threading.Thread(target=server_tool.tcp_link, args=(sock, addr))
        thread.start()
        self.addr_text_signal.emit(addr)  # HERE
        # Finish recept client, go next
        self.receptionist_working_signal.emit(True)

    @QtCore.pyqtSlot(bool)
    def close(self):
        self.open = False
        self.receptionist_thread.quit()  # quit thread
        print('Server closed!')


# Worker for controlling the server
class ServerWorker(QObject):
    start_signal = QtCore.pyqtSignal(bool)
    close_signal = QtCore.pyqtSignal(bool)
    addr_to_ui_signal = QtCore.pyqtSignal(tuple)

    def __init__(self):
        super(ServerWorker, self).__init__()
        host_ip = get_host_ip()
        host_ip = "127.0.0.1"
        self.server = Server(host_ip, 8080)
        self.server.addr_text_signal.connect(self.receive_addr_from_server)

        self.start_signal.connect(self.server.start)
        self.close_signal.connect(self.server.close)

    @QtCore.pyqtSlot(bool)
    def start_or_close_server(self, signal):
        print('Ask server to', signal)
        if signal:
            # Start server
            self.start_signal.emit(True)
            # Add server.start into a new Thread
            # t = threading.Thread(target=self.server.start)
            # t.start()
        else:
            # Close server
            # That Thread will finish and exit
            self.close_signal.emit(True)

    @QtCore.pyqtSlot(tuple)
    def receive_addr_from_server(self, signal):
        # print('Received signal:', signal)
        self.addr_to_ui_signal.emit(signal)


# Database manage worker
class DatabaseWorker(QObject):
    blacklist_result_signal = QtCore.pyqtSignal(list)

    def __init__(self, host='localhost', user='root', passwd='', database_name='test'):
        super(DatabaseWorker, self).__init__()

        self.database = None
        self.database_state = 0
        self.host = host
        self.user = user
        self.passwd = passwd
        self.database_name = database_name

    @QtCore.pyqtSlot(bool)
    def start_or_close_database(self, signal):
        if signal:
            try:
                if self.database_state == 0:
                    self.database = mysql.connector.connect(
                        host=self.host,
                        user=self.user,
                        passwd=self.passwd,
                        database=self.database_name
                    )
                    self.create_table()
                else:
                    print('An existed database connection!')
            except mysql.connector.Error as err:
                print(err)
            else:
                self.database_state = 1
                print('Connect Success!')
        else:
            try:
                if self.database_state == 1:
                    self.database.close()
                else:
                    print('No database connection now!')
            except mysql.connector.Error as err:
                print(err)
            else:
                self.database_state = 0
                print('Disconnect Success!')

    def create_table(self):
        create_table_sql = 'CREATE TABLE IF NOT EXISTS blacklist (ipaddr VARCHAR(100))'
        cursor_object = self.database.cursor()
        cursor_object.execute(create_table_sql)
        self.database.commit()
        cursor_object.close()

    @QtCore.pyqtSlot(str)
    def insert_addr(self, addr):
        try:
            print(addr, 'will be added to database')
            insert_addr_sql = 'INSERT INTO blacklist (ipaddr) VALUES ("' + addr + '")'
            print('SQL:', insert_addr_sql)
            cursor_object = self.database.cursor()
            cursor_object.execute(insert_addr_sql)
            self.database.commit()  # submit modified
            cursor_object.close()
        except mysql.connector.Error as err:
            print(err)
        else:
            print('New address inserted')

    @QtCore.pyqtSlot(str)
    def delete_addr(self, addr):
        try:
            print(addr, 'will be deleted in database')
            delete_addr_sql = 'DELETE FROM blacklist WHERE ipaddr="' + addr + '"'
            print('SQL:', delete_addr_sql)
            cursor_object = self.database.cursor()
            cursor_object.execute(delete_addr_sql)
            self.database.commit()  # submit modified
            cursor_object.close()
        except mysql.connector.Error as err:
            print(err)
        else:
            print(addr, 'deleted')

    @QtCore.pyqtSlot(bool)
    def search_blacklist(self):
        searching_sql = 'SELECT * FROM blacklist'
        cursor_object = self.database.cursor()
        cursor_object.execute(searching_sql)
        searching_result = cursor_object.fetchall()
        # Send back to UI
        self.blacklist_result_signal.emit(searching_result)
        cursor_object.close()


class MainWindow(QMainWindow):
    # - signal - Can't work in super(MainWindow, self).__init__()
    monitor_worker_signal = QtCore.pyqtSignal(bool)
    start_or_close_signal = QtCore.pyqtSignal(bool)
    database_soc_signal = QtCore.pyqtSignal(bool)
    database_search_signal = QtCore.pyqtSignal(bool)
    database_insert_signal = QtCore.pyqtSignal(str)
    database_delete_signal = QtCore.pyqtSignal(str)

    def __init__(self):
        super(MainWindow, self).__init__()

        # Window information
        self.setWindowTitle("My Server")
        self.setFixedWidth(600)

        # Server information
        # logging.info('######## Server Initializing... ########')
        self.server_status = False  # False -> Close; True -> Open
        self.log_text = 'Log output:\n'

        # Initialize the server worker
        self.server_worker = ServerWorker()
        self.start_or_close_signal.connect(self.server_worker.start_or_close_server)  # Link order to worker
        self.server_worker.addr_to_ui_signal.connect(self.receive_connected_client_addr)
        self.server_thread = QThread()
        self.server_worker.moveToThread(self.server_thread)
        self.server_thread.start()

        main_widget = QWidget()
        main_layout = QHBoxLayout()

        server_layout = QVBoxLayout()

        # Resource allocation situation (CPU & RAM)
        self.monitor_worker = MonitorWorker()  # create a worker (thread)
        # - cpu
        self.monitor_worker.cpu_signals.connect(self.monitor_os_resource_cpu)  # Link work's result to screen
        self.monitor_worker_signal.connect(self.monitor_worker.run_cpu_usage)  # Link run order to worker
        # - ram
        self.monitor_worker.ram_signals.connect(self.monitor_os_resource_ram)  # Link work's result to screen
        self.monitor_worker_signal.connect(self.monitor_worker.run_ram_usage)  # Link run order to worker
        # - thread
        self.monitor_thread = QThread()
        self.monitor_worker.moveToThread(self.monitor_thread)
        self.monitor_thread.start()
        # - layout
        os_resource_usage_layout = QHBoxLayout()
        self.cpu_usage_label = QLabel()
        self.cpu_usage_label.setText('CPU: xx%')
        self.cpu_usage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ram_usage_label = QLabel()
        self.ram_usage_label.setText('RAM: xx%')
        self.ram_usage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        os_resource_usage_layout.addWidget(self.cpu_usage_label)
        os_resource_usage_layout.addWidget(self.ram_usage_label)
        # - active worker
        self.monitor_worker_signal.emit(True)  # start to work

        # Open / Close server
        self.server_gate_button = QPushButton()
        self.server_gate_button.setText('Open Server')  # Initial status is Close and its text is Open
        self.server_gate_button.clicked.connect(self.set_server_status)

        # Log output
        self.log_text_window = QTextEdit()
        self.log_text_window.setText(self.log_text)

        server_layout.addLayout(os_resource_usage_layout)
        server_layout.addWidget(self.server_gate_button)
        server_layout.addWidget(self.log_text_window)

        # Database part ->

        # Database worker initialize
        self.blacklist = list()
        self.database_worker = DatabaseWorker()
        # Signal connection
        self.database_soc_signal.connect(self.database_worker.start_or_close_database)
        self.database_search_signal.connect(self.database_worker.search_blacklist)
        self.database_worker.blacklist_result_signal.connect(self.receive_blacklist_results)
        self.database_insert_signal.connect(self.database_worker.insert_addr)
        self.database_delete_signal.connect(self.database_worker.delete_addr)
        # Add to thead
        self.database_thread = QThread()
        self.database_worker.moveToThread(self.database_thread)
        self.database_thread.start()

        # Database layout
        database_layout = QVBoxLayout()
        # - button
        self.database_gate_button = QPushButton()
        self.database_gate_button.setText('Open Database')
        self.database_gate_button.clicked.connect(self.set_database_status)
        # - insert new addr
        input_addr_layout = QHBoxLayout()
        self.input_addr_box = QLineEdit()
        self.input_addr_button = QPushButton()
        self.input_addr_button.setText('Add')
        self.input_addr_button.clicked.connect(self.insert_new_addr)
        input_addr_layout.addWidget(self.input_addr_box)
        input_addr_layout.addWidget(self.input_addr_button)
        # - delete an addr
        delete_addr_layout = QHBoxLayout()
        self.delete_addr_box = QLineEdit()
        self.delete_addr_button = QPushButton()
        self.delete_addr_button.setText('Del')
        self.delete_addr_button.clicked.connect(self.delete_addr)
        delete_addr_layout.addWidget(self.delete_addr_box)
        delete_addr_layout.addWidget(self.delete_addr_button)
        # - total number of black address
        self.blacklist_counter = QLabel()
        self.blacklist_counter.setText('Total: None')
        self.blacklist_counter.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # - list of blacklist
        self.blacklist_box = QTextEdit()
        self.blacklist_box.setText('Please open the database...')

        database_layout.addWidget(self.database_gate_button)
        database_layout.addLayout(input_addr_layout)
        database_layout.addLayout(delete_addr_layout)
        database_layout.addWidget(self.blacklist_counter)
        database_layout.addWidget(self.blacklist_box)

        main_layout.addLayout(server_layout, stretch=1)
        main_layout.addLayout(database_layout, stretch=1)

        main_widget.setLayout(main_layout)

        # upload to main window
        self.setCentralWidget(main_widget)

        self.show()

    def set_database_status(self):

        if self.database_worker.database_state == 1:
            # Ture off the database
            self.database_soc_signal.emit(False)
            self.database_gate_button.setText('Open Database')

            self.log_text += 'Database closed' + '\n'
            self.log_text_window.setText(self.log_text)
            logging.info('######## Database closed ########')

        else:
            # Ture on the database
            self.database_soc_signal.emit(True)
            self.database_gate_button.setText('Close Database')
            # Get the contents of blacklist
            self.database_search_signal.emit(True)

            self.log_text += 'Database started' + '\n'
            self.log_text_window.setText(self.log_text)
            logging.info('######## Database started ########')

    def insert_new_addr(self):
        if self.database_worker.database_state == 1:
            new_addr = self.input_addr_box.text()
            self.database_insert_signal.emit(new_addr)
            # Wait 1 sec
            self.input_addr_button.setCheckable(False)
            self.database_search_signal.emit(True)  # Update Database
            time.sleep(0.5)
            self.input_addr_button.setCheckable(True)
            self.log_text += new_addr + ' was added to blacklist' + '\n'
            self.log_text_window.setText(self.log_text)
            logging.info('######## ' + new_addr + ' was added to blacklist ########')
        else:
            self.log_text += 'Please open the database first!' + '\n'
            self.log_text_window.setText(self.log_text)

    def delete_addr(self):
        if self.database_worker.database_state == 1:
            delete_addr = self.delete_addr_box.text()
            self.database_delete_signal.emit(delete_addr)
            # Wait 1 sec
            self.delete_addr_button.setCheckable(False)
            self.database_search_signal.emit(True)  # Update Database
            time.sleep(0.5)
            self.delete_addr_button.setCheckable(True)
            self.log_text += delete_addr + ' was removed from blacklist' + '\n'
            self.log_text_window.setText(self.log_text)
            logging.info('######## ' + delete_addr + ' was removed from blacklist ########')
        else:
            self.log_text += 'Please open the database first!' + '\n'
            self.log_text_window.setText(self.log_text)

    @QtCore.pyqtSlot(list)
    def receive_blacklist_results(self, signal):
        # print('blacklist results:', signal)  # eg. [('137.0.0.1',), ('137.0.0.2',)]
        self.blacklist = [addr[0] for addr in signal]
        # Update to blacklist box
        self.blacklist_counter.setText('Total: ' + str(len(self.blacklist)))
        self.blacklist_counter.setText('Total: ' + str(len(self.blacklist)))
        tmp_box = 'blacklist address:\n'
        for addr in self.blacklist:
            tmp_box += addr
            tmp_box += '\n'
        self.blacklist_box.setText(tmp_box)
        print(self.blacklist)

    def set_server_status(self):

        if self.server_status:
            # Ture off the server
            self.start_or_close_signal.emit(False)
            self.server_status = False
            self.server_gate_button.setText('Open Server')
            logging.info('######## Server Closing... ########')
        else:
            # Ture on the server
            self.start_or_close_signal.emit(True)
            self.server_status = True
            self.server_gate_button.setText('Close Server')
            logging.info('######## Server Starting... ########')

        self.log_text += 'Current server status: ' + str(self.server_status) + '\n'
        # self.log_text += 'IP address: ' + get_host_ip() + '\n'
        self.log_text += 'Port: 8080' + '\n'
        self.log_text_window.setText(self.log_text)

    @QtCore.pyqtSlot(tuple)
    def receive_connected_client_addr(self, signal):
        print('Received signal:', signal)
        addr = signal[0]
        port = signal[1]
        self.log_text += 'New connection, IP: ' + str(addr) + '; port: ' + str(port) + '\n'
        self.log_text_window.setText(self.log_text)

    def monitor_os_resource_cpu(self, signals):
        self.cpu_usage_label.setText('CPU: ' + str(signals) + '%')
        self.monitor_worker_signal.emit(True)

    def monitor_os_resource_ram(self, signals):
        self.ram_usage_label.setText('RAM: ' + str(signals) + '%')
        self.monitor_worker_signal.emit(True)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    app.exec()  # it starts an event loop and creates a thread that is referred to as the main thread
