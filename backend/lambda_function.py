import json
import os
import sqlite3
import hashlib
from datetime import datetime

# 26.07.09 재업로두
# Global flag to track connection type
IS_SQLITE = True

def get_db_connection():
    global IS_SQLITE
    
    db_host = os.environ.get('DB_HOST')
    db_user = os.environ.get('DB_USER')
    db_password = os.environ.get('DB_PASSWORD')
    db_name = os.environ.get('DB_NAME')
    
    if db_host and db_user and db_password and db_name:
        try:
            import pymysql
            conn = pymysql.connect(
                host=db_host,
                user=db_user,
                password=db_password,
                database=db_name,
                port=int(os.environ.get('DB_PORT', 3306)),
                cursorclass=pymysql.cursors.DictCursor
            )
            IS_SQLITE = False
            return conn
        except ImportError:
            print("pymysql library not found. Falling back to SQLite.")
        except Exception as e:
            print(f"Failed to connect to MySQL RDS ({e}). Falling back to SQLite.")
            
    # SQLite Fallback
    # AWS Lambda allows writing only to /tmp directory
    db_path = 'lambda_app.db'
    if 'LAMBDA_TASK_ROOT' in os.environ:
        db_path = '/tmp/lambda_app.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    IS_SQLITE = True
    return conn

def execute_query(conn, query, params=None, fetch='all', commit=False):
    if params is None:
        params = ()
        
    if IS_SQLITE:
        query = query.replace('%s', '?')
        
    cursor = conn.cursor()
    cursor.execute(query, params)
    
    result = None
    if fetch == 'all':
        rows = cursor.fetchall()
        if IS_SQLITE:
            result = [dict(row) for row in rows]
        else:
            result = list(rows)
    elif fetch == 'one':
        row = cursor.fetchone()
        if row:
            result = dict(row) if IS_SQLITE else row
            
    if commit:
        conn.commit()
        
    cursor.close()
    return result

def init_db():
    conn = get_db_connection()
    if IS_SQLITE:
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            created_at VARCHAR(50) NOT NULL,
            last_login_at VARCHAR(50)
        )
        """
    else:
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            created_at VARCHAR(50) NOT NULL,
            last_login_at VARCHAR(50)
        )
        """
    execute_query(conn, create_table_sql, commit=True)
    
    # Pre-seed Admin account if not exists
    admin_email = "admin@admin.com"
    existing_admin = execute_query(
        conn, 
        "SELECT * FROM users WHERE email = %s", 
        (admin_email,), 
        fetch='one'
    )
    if not existing_admin:
        admin_pass_hash = hashlib.sha256("admin123".encode()).hexdigest()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        execute_query(
            conn,
            "INSERT INTO users (email, password, role, created_at) VALUES (%s, %s, %s, %s)",
            (admin_email, admin_pass_hash, "admin", now),
            commit=True
        )
        
    conn.close()

def build_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
        },
        "body": json.dumps(body)
    }

def lambda_handler(event, context):
    # Initialize the database table
    try:
        init_db()
    except Exception as e:
        return build_response(500, {"error": f"Database initialization failed: {str(e)}"})
        
    # Get request path and method (support REST API / ALB / HTTP API formats)
    path = event.get('path') or event.get('rawPath', '')
    method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', '')
    
    if not path or not method:
        return build_response(400, {"error": "Missing request path or HTTP method"})
        
    # Standardize options request for CORS preflight
    if method.upper() == 'OPTIONS':
        return build_response(200, {"message": "CORS preflight successful"})

    # Parse request body
    body = {}
    event_body = event.get('body')
    if event_body:
        try:
            body = json.loads(event_body)
        except Exception:
            # If body is already parsed (e.g. from local server or custom caller)
            if isinstance(event_body, dict):
                body = event_body
            else:
                return build_response(400, {"error": "Invalid JSON body format"})

    conn = get_db_connection()
    
    try:
        # Route: POST /api/signup
        if path == '/api/signup' and method.upper() == 'POST':
            email = body.get('email', '').strip()
            password = body.get('password', '')
            
            if not email or not password:
                return build_response(400, {"error": "Email and password are required"})
                
            if len(password) < 6:
                return build_response(400, {"error": "Password must be at least 6 characters long"})
                
            # Check if email already exists
            existing_user = execute_query(conn, "SELECT id FROM users WHERE email = %s", (email,), fetch='one')
            if existing_user:
                return build_response(400, {"error": "Email is already registered"})
                
            # Determine role (if admin@example.com, set as admin, otherwise user)
            role = "admin" if email == "admin@example.com" else "user"
            
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            execute_query(
                conn,
                "INSERT INTO users (email, password, role, created_at) VALUES (%s, %s, %s, %s)",
                (email, password_hash, role, now),
                commit=True
            )
            
            return build_response(201, {
                "message": "User registered successfully",
                "email": email,
                "role": role
            })
            
        # Route: POST /api/login
        elif path == '/api/login' and method.upper() == 'POST':
            email = body.get('email', '').strip()
            password = body.get('password', '')
            
            if not email or not password:
                return build_response(400, {"error": "Email and password are required"})
                
            if len(password) < 6:
                return build_response(400, {"error": "Password must be at least 6 characters long"})
                
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            user = execute_query(
                conn,
                "SELECT * FROM users WHERE email = %s AND password = %s",
                (email, password_hash),
                fetch='one'
            )
            
            if not user:
                return build_response(401, {"error": "Invalid email or password"})
                
            # Update last login time
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            execute_query(
                conn,
                "UPDATE users SET last_login_at = %s WHERE id = %s",
                (now, user['id']),
                commit=True
            )
            
            return build_response(200, {
                "message": "Login successful",
                "email": user['email'],
                "role": user['role'],
                "created_at": user['created_at']
            })
            
        # Route: GET /api/members (Admin Only)
        elif path == '/api/members' and method.upper() == 'GET':
            # For simplicity, admin identity is verified via custom header "X-User-Role" and "X-User-Email"
            # In production, this would verify JWT tokens or session cookies
            requester_role = event.get('headers', {}).get('X-User-Role') or event.get('headers', {}).get('x-user-role')
            requester_email = event.get('headers', {}).get('X-User-Email') or event.get('headers', {}).get('x-user-email')
            
            if requester_role != 'admin' or requester_email != 'admin@example.com':
                return build_response(403, {"error": "Access denied. Admin role required."})
                
            # Query all members
            users = execute_query(conn, "SELECT email, created_at, last_login_at FROM users ORDER BY created_at DESC")
            return build_response(200, {"members": users})
            
        # Route: GET /api/member (Regular user details)
        elif path == '/api/member' and method.upper() == 'GET':
            requester_email = event.get('headers', {}).get('X-User-Email') or event.get('headers', {}).get('x-user-email')
            
            if not requester_email:
                return build_response(401, {"error": "Unauthorized. Sign-in required."})
                
            user = execute_query(
                conn,
                "SELECT email, created_at FROM users WHERE email = %s",
                (requester_email,),
                fetch='one'
            )
            
            if not user:
                return build_response(404, {"error": "User not found"})
                
            return build_response(200, user)
            
        else:
            return build_response(404, {"error": f"API endpoint not found: {method} {path}"})
            
    except Exception as e:
        return build_response(500, {"error": f"Internal server error: {str(e)}"})
        
    finally:
        conn.close()
