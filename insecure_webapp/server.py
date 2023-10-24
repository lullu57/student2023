import os
import psycopg2
from flask import Flask, abort, Response, request, jsonify
import subprocess
import hashlib

ALLOWED_EXTENSIONS = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "text/javascript",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
}

app = Flask(__name__, static_folder="")
app.url_map.strict_slashes = False

PG_HOST = os.getenv("PGHOST")
PG_DATABASE = os.getenv("PGDATABASE")
PG_USER = os.getenv("PGUSER")
PG_PASSWORD = os.getenv("PGPASSWORD")
PG_CONNECT_STRING = " ".join(
    (
        f"dbname='{PG_DATABASE}'",
        f"user='{PG_USER}'",
        f"host='{PG_HOST}'",
        f"password='{PG_PASSWORD}'",
    )
)

print(PG_CONNECT_STRING)

def secure_path(path):
    """
    Return a secure version of the path, or None if the path is insecure.
    """
    normalized_path = os.path.normpath(path)
    if os.path.isabs(normalized_path) or normalized_path.startswith('..'):
        return None
    return normalized_path

def run_query(query):
    try:
        conn = psycopg2.connect(PG_CONNECT_STRING)
        with conn.cursor() as curs:
            try:
                curs.execute(query)
                conn.commit()
                rows = curs.fetchmany(100)
                return rows
            except (Exception, psycopg2.DatabaseError) as error:
                return [str(error)]
    except (Exception, psycopg2.DatabaseError) as error:
        return ["Conection failed"]
    return None


def get_comments_html():
    data = []
    rows = run_query("SELECT text, author FROM comments")
    for row in rows:
        if type(row) is str:
            data.append("" + row)
        else:
            comment, author = row[0], row[1]
            row = " - ".join(row)
            data.append(f'<div class="comment">{comment}<div class="author">- {author}</div></div>')
    return "<br />\n".join(data)

def send_file(path):
    print("send_file path:", path)

    if path in {"index", "/", "/index", "/index.html", "index.html"}:
        with open("index.html", "r") as f:
            content = f.read()
            content = content.replace("Comments are loading...", get_comments_html())
            return Response(content, mimetype="text/html")

    if path.startswith("/static/"):
        path = path[len("/static/"):]

    # Secure the path
    path = secure_path(path)
    if path is None:
        abort(404)

    # Check if path is a directory
    if os.path.isdir(path):
        paths = [os.path.join(path, x) for x in os.listdir(path)]
        return Response("\n".join(paths), mimetype="text/plain")

    # Determine mimetype based on file extension
    ext = os.path.splitext(path)[1]
    mimetype = ALLOWED_EXTENSIONS.get(ext, "text/plain")

    try:
        with open(path, "r") as f:
            return Response(f.read(), mimetype=mimetype)
    except FileNotFoundError:
        pass

    if not path.endswith(".html"):
        try:
            with open(path + ".html", "r") as f:
                return Response(f.read(), mimetype="text/html")
        except FileNotFoundError:
            pass

    abort(404)


def complete_login(username, password):
    # This function completes a login
    # (username and password have already been verified)

    # Generate session token:
    h = hashlib.sha256()
    h.update(username.encode("utf-8"))
    h.update(password.encode("utf-8"))
    session = h.hexdigest()

    # Update session token in database
    results = run_query(
        f"INSERT INTO users(username, password, session) "
        + f"VALUES('{username}', '{password}', '{session}') "
        + f"ON CONFLICT(username) DO UPDATE SET session = '{session}';"
    )
    print("Database response:")
    print(results)
    return jsonify({"username": username, "password": password, "session": session})


@app.route("/api/login", methods=["POST"])
def login_api():
    content = request.json
    if "username" not in content or "password" not in content:
        abort(404)

    # Get the appropriate user:
    username = content["username"]
    password = content["password"]
    print(f"username: '{username}' password: '{password}'")

  

    # Check if password is correct:
    results = run_query(
        f"SELECT username, password, session "
        + f"FROM users "
        + f"WHERE username='{username}';"
    )

    if len(results) > 0:
        print(results)
        if password != results[0][1]:
            abort(404)

    return complete_login(username, password)


@app.route("/api/comments", methods=["POST"])
def comments_api():
    content = request.json
    if "username" not in content or "comment" not in content:
        abort(404)

    # Get the appropriate user:
    username = content["username"]
    results = run_query(
        f"SELECT username, password, session "
        + f"FROM users "
        + f"WHERE username='{username}';"
    )

    # Update session token in database
    results = run_query(
        f"INSERT INTO comments(author, text) "
        + f"VALUES('{content['username']}', '{content['comment']}');"
    )
    print("Database response:")
    print(results)
    print("User object:")
    print(str(content))
    return jsonify(content)


@app.route("/comments")
def comments():
    return get_comments_html()


@app.route("/calendar")
@app.route("/calendar/<string:year>")
@app.route("/calendar/<string:year>/<string:month>")
def calendar(year=None, month=None):
    command = "cal"
    if month:
        command += " " + month
    if year:
        command += " " + year
    output = subprocess.check_output(command, shell=True).decode("utf-8").rstrip()
    return Response(output, mimetype="text/plain")


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/static")
@app.route("/static/<path:file>")
@app.route("/<path:file>") # Path which includes slashes
@app.route("/<string:file>") # Just a filename
def serve_static_files(file=""):
    return send_file(file)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
