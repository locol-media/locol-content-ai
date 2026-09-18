import sqlite3
import uuid
import time
import bcrypt
from datetime import datetime
from typing import Dict, Any, Optional
from user_models import RegisterUserRequest, RegisterUserResponse, LoginUserRequest, LoginUserResponse

DATABASE_PATH = "./db/persistent_data.sqlite"

def _hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt (cost factor 12)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))

def generate_uuid_v7() -> str:
    """Generate a UUID v7 (time-ordered UUID)"""
    # UUID v7 format: timestamp (48 bits) + version (4 bits) + random (12 bits) + variant (2 bits) + random (62 bits)
    timestamp_ms = int(time.time() * 1000)  # Current timestamp in milliseconds
    
    # Create UUID v7 manually since Python's uuid module doesn't support v7 yet
    # We'll use uuid4 and modify it to be time-ordered
    base_uuid = uuid.uuid4()
    
    # Replace the first 48 bits with timestamp
    time_high = (timestamp_ms >> 16) & 0xFFFFFFFF
    time_mid = (timestamp_ms >> 4) & 0x0FFF
    time_low = (timestamp_ms & 0x0F) << 12 | (base_uuid.time_low & 0x0FFF)
    
    # Set version to 7
    time_low = (time_low & 0x0FFF) | 0x7000
    
    # Create new UUID with time-ordered components
    uuid_int = (time_high << 96) | (time_mid << 80) | (time_low << 64) | (base_uuid.clock_seq_hi_variant << 56) | (base_uuid.clock_seq_low << 48) | base_uuid.node
    return str(uuid.UUID(int=uuid_int))

def init_users_table():
    """Initialize the users table if it doesn't exist (with UUID v7)"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    
    conn.commit()
    conn.close()

def register_user(request: RegisterUserRequest) -> RegisterUserResponse:
    """Register a new user in the database"""
    try:
        init_users_table()
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check if username already exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (request.username,))
        if cursor.fetchone():
            return RegisterUserResponse(
                success=False,
                message="Username is already taken. Please choose a different username."
            )
        
        # Generate UUID v7 for new user
        user_id = generate_uuid_v7()
        
        # Insert new user
        cursor.execute("""
            INSERT INTO users (id, username, email, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, request.username, request.email, _hash_password(request.password), request.created_at))
        conn.commit()
        conn.close()
        
        # Initialize user-specific database
        from db_manager import init_user_database
        init_user_database(user_id)

        # Swap the freshly seeded default LLM over to a per-user Bifrost virtual key.
        # provision_default_llm() swallows its own failures, but an import error would
        # still escape and cost the caller an account they've already been charged for.
        try:
            from bifrost_manager import provision_default_llm
            provision_default_llm(user_id, request.username)
        except Exception as e:
            print(f"[Bifrost] Provisioning skipped for user {user_id}: {e}")

        return RegisterUserResponse(
            success=True,
            message="User registered successfully",
            user_id=user_id
        )
        
    except Exception as e:
        return RegisterUserResponse(
            success=False,
            message="Registration failed",
            error=str(e)
        )

def login_user(request: LoginUserRequest) -> LoginUserResponse:
    """Authenticate user login"""
    try:
        init_users_table()
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Find user by username; verification happens in Python since bcrypt
        # hashes are salted and can't be matched with SQL '='.
        cursor.execute("""
            SELECT id, password_hash
            FROM users
            WHERE username = ? AND is_active = 1
        """, (request.username,))

        user = cursor.fetchone()

        if user is None:
            conn.close()
            return LoginUserResponse(
                success=True,
                authenticated=False,
                message="Invalid username or password"
            )

        user_id, stored_hash = user

        try:
            password_ok = _verify_password(request.password, stored_hash)
        except ValueError:
            # Not a valid bcrypt hash (e.g. a row predating bcrypt) — there's no
            # way to verify against it, so treat it as a failed login.
            password_ok = False

        if not password_ok:
            conn.close()
            return LoginUserResponse(
                success=True,
                authenticated=False,
                message="Invalid username or password"
            )

        # Update last login time
        cursor.execute("""
            UPDATE users
            SET last_login = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), user_id))

        conn.commit()
        conn.close()

        return LoginUserResponse(
            success=True,
            authenticated=True,
            message="Login successful",
            user_id=user_id
        )
            
    except Exception as e:
        return LoginUserResponse(
            success=False,
            authenticated=False,
            message="Login failed",
            error=str(e)
        )

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user information by ID"""
    try:
        init_users_table()
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, username, email, created_at, last_login, is_active
            FROM users 
            WHERE id = ? AND is_active = 1
        """, (user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {
                "id": user[0],
                "username": user[1],
                "email": user[2],
                "created_at": user[3],
                "last_login": user[4],
                "is_active": user[5]
            }
        else:
            return None
            
    except Exception as e:
        print(f"Error getting user by ID: {e}")
        return None