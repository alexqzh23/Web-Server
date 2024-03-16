import os
import os.path
import time
import pymysql
import logging

# Log configuration
logging.basicConfig(filename='./server.log', filemode='a', level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def tcp_link(sock, addr):
    status = get_status(addr)
    print(status)

    response_headers = "HTTP/1.1 200 OK\r\n"
    response_headers += "\r\n"

    request_data = sock.recv(1024).decode("utf-8")  # 1024 indicates the maximum number of bytes received this time
    request_line = request_data.splitlines()[0]

    HTTP_method = request_line.split()[0]
    path = request_line.split()[1]

    if path != '/favicon.ico':
        logging.info('######## one request line from ' + addr[0] + ': ' + request_line + '... ########')

    if HTTP_method == "POST":
        userinfo = request_data.splitlines()[-1].split('&')
        username = userinfo[0][9:]
        password = userinfo[1][9:]
        print(username, password)

        db = pymysql.connect(host='localhost', user='root', password='',
                             port=3306, db='test', charset='utf8')

        # Enable the cursor function of mysql and create a cursor object
        cursor = db.cursor()

        sql = "select * from admins"

        # Execute SQL statement
        cursor.execute(sql)

        # Get a list of all records
        results = cursor.fetchall()

        print(results)

        flag = 0
        for row in results:
            if row[1] == username:
                if row[2] == password:
                    flag = 1
                    cursor.execute('update admins set ipaddr=%s where username=%s and password=%s',
                                   (addr[0], row[1], row[2]))
                    db.commit()
        db.close()

        # There are matching results
        if flag == 1:
            response_body = """<!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta http-equiv="X-UA-Compatible" content="IE=edge">
                    <title>Login successfully</title>
                    <style>
                    .center {
                        padding: 230px 0;
                        border: 3px solid black;
                        text-align: center;
                    }
                    </style>
                </head>
                <body class="center">
                    <h1>Login successfully!</h1>
                    <a href="../">Go to Admin home</a>
                </body>
            </html>
                        """
            sock.send(response_headers.encode("utf-8"))
            sock.send(response_body.encode("utf-8"))
        else:
            response_body = """<!DOCTYPE html>
    <html>

    <head>
        <meta charset="utf-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <title>Login failed</title>
        <style>
        .center {
            padding: 230px 0;
            border: 3px solid black;
            text-align: center;
        }
        </style>
    </head>
    <body class="center">
        <h1>Login failed!</h1>
        <a href="javascript:history.go(-1);">Back</a>
    </body>
</html>
            """
            sock.send(response_headers.encode("utf-8"))
            sock.send(response_body.encode("utf-8"))

    else:
        if path == '/favicon.ico':
            return

        user_status = get_status(addr)

        if user_status == 1:
            sock.send(response_headers.encode("utf-8"))
            response_body = """<!DOCTYPE html>
                <html>

                <head>
                    <meta charset="utf-8">
                    <meta http-equiv="X-UA-Compatible" content="IE=edge">
                    <title>Permission denied</title>
                    <style>
                    .center {
                        padding: 230px 0;
                        border: 3px solid black;
                        text-align: center;
                    }
                    </style>
                </head>
                <body class="center">
                    <h1>Permission denied!</h1>
                    <a href="javascript:history.go(-1);">Back</a>
                </body>
            </html>
                        """
            sock.send(response_body.encode("utf-8"))
            sock.close()
            return

        if path == '/':
            sock.send(response_headers.encode("utf-8"))
            if user_status == 0:
                sock.send(get_resources('./resources', user_status).encode("utf-8"))
            if user_status == 2:
                sock.send(get_resources('./', user_status).encode("utf-8"))

        else:
            if user_status == 0:
                path = path.replace("\\", "/")
                pathsplit = path.split('/')
                print(pathsplit)
                if pathsplit[1] != 'resources' and pathsplit[1] != 'login':
                    response_body = """<!DOCTYPE html>
                        <html>

                        <head>
                            <meta charset="utf-8">
                            <meta http-equiv="X-UA-Compatible" content="IE=edge">
                            <title>Permission denied</title>
                            <style>
                            .center {
                                padding: 230px 0;
                                border: 3px solid black;
                                text-align: center;
                            }
                            </style>
                        </head>
                        <body class="center">
                            <h1>Permission denied!</h1>
                            <a href="javascript:history.go(-1);">Back</a>
                        </body>
                    </html>
                                """
                    sock.send(response_headers.encode("utf-8"))
                    sock.send(response_body.encode("utf-8"))
                    sock.close()
                    return

            path = path.replace("\\", "/")
            pathsplit = path.split('/')
            if '.' in pathsplit[-1]:  # get files
                file_name = path  # Set the read file path
                with open('.' + file_name, "rb") as f:  # Read file contents in binary
                    response_body = f.read()
                sock.send(response_headers.encode("utf-8"))  # Transcoding utf-8 and sending data to the browser
                sock.send(response_body)
            else:  # Get the directory under the folder
                sock.send(response_headers.encode("utf-8"))
                sock.send(get_resources(path, user_status).encode("utf-8"))

    sock.close()


def get_resources(folder, user_status):
    if user_status == 0:
        filecontent = '''<!DOCTYPE html>
    <html>
    
    <head>
        <meta charset="utf-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <title>MiniServer</title>
    </head>
    <body>
        <h1>Web Server</h1>
        <input type="button" value="Admin Login" class="button_active" onclick="location.href='../login/login.html'" /><br /><br />
        <table border="0">
            <tr>
                <td style="width:150px">Filename</td>
                <td style="width:150px">Size</td>
                <td style="width:200px">Modification time</td>
            </tr>
            </body>
            '''
    else:
        filecontent = '''<!DOCTYPE html>
    <html>
    
    <head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>MiniServer</title>
    </head>
    <body>
    <h1>Web Server</h1>
    <table border="0">
        <tr>
            <td style="width:150px">Filename</td>
            <td style="width:150px">Size</td>
            <td style="width:200px">Modification time</td>
        </tr>
        </body>
        '''

    dir = folder
    if dir[0] != '.':
        dir = '.' + dir
    resourcelist = os.listdir(dir)  # List all directories and files under the folder
    for filename in resourcelist:
        pathTmp = os.path.join(dir, filename)  # Get the combined path and filename
        filecontent = filecontent + '<tr>'
        pathTmp = pathTmp.replace("\\", "/")
        pathsplit = pathTmp.split('/')
        filecontent = filecontent + '<td><a href = "./' + pathsplit[-2] + "/" + pathsplit[
            -1] + '">' + filename + '</a></td>'

        filecontent = filecontent + '<td>'
        if os.path.isfile(pathTmp): # Judge whether it is a file
            filesize = os.path.getsize(pathTmp)  # If it is a file, get the size of the corresponding file
            filecontent = filecontent + str(format(filesize / 1024, '.2f')) + ' KB'
            filecontent = filecontent + '</td>'

        filecontent = filecontent + '<td>'
        mtime = os.stat(pathTmp).st_mtime
        file_modify_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
        filecontent = filecontent + file_modify_time
        filecontent = filecontent + '</td>'

    filecontent += '</table></body>\n</html>'

    return filecontent


def get_status(addr):
    status = 0
    db = pymysql.connect(host='localhost', user='root', password='',
                         port=3306, db='test', charset='utf8')
    cursor = db.cursor()

    sql = "select * from blacklist"
    cursor.execute(sql)

    results = cursor.fetchall()
    print(results)
    for row in results:
        if row[0] == addr[0]:
            status = 1
            db.close()
            return status

    sql = "select * from admins"
    cursor.execute(sql)

    results = cursor.fetchall()
    print(results)
    for row in results:
        if row[3] == addr[0]:
            status = 2

    db.close()
    return status
