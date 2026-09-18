# How we store passwords

This is a plain-English explanation of what happens to your password when you
register or log in to Locol Content AI, written so you don't need a security background to
follow it. Every claim links to the code that backs it, so a developer can check the
explanation against reality.

Almost everything described here lives in one file:
[`BackEnd/src/user_management.py`](../BackEnd/src/user_management.py).

## 1. The short version

**We never store your password.** Not encrypted, not hidden, not obfuscated — we
simply don't keep it.

What we keep instead is a *fingerprint* of it. When you pick a password, we run it
through a one-way scrambler and store only the scrambled result. The scrambling is
one-way in the same sense that a paper shredder is: turning the page into confetti is
easy, turning the confetti back into the page is not. A safe would be the wrong
analogy — a safe implies there's a key somewhere that opens it. There is no key here.
Nobody at Locol Content AI can look up your password, and neither can anyone who steals the
database.

That raises an obvious question — if we don't know your password, how do we check it
when you log in? Section 4 answers that.

## 2. What actually gets stored

User accounts live in a single SQLite table, created by `init_users_table()` at
[user_management.py:40-58](../BackEnd/src/user_management.py#L40-L58):

```sql
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_login TEXT,
    is_active BOOLEAN DEFAULT 1
)
```

Note the column name: `password_hash`, not `password`. There is no `password` column
anywhere in this project, and no `salt` column either — you'll see why in a moment.

A stored value looks like this — 60 characters, and this is the *entire* record of a
user's password:

```
$2b$12$Nt7kQxV1cJ8pL0hZbW3sSuk9rTgYf2mQeD4vXhA6oPjR8sKwLcE1a
```

It breaks into three parts, separated by `$`:

| Part | Meaning |
|---|---|
| `2b` | which scrambling algorithm was used — bcrypt |
| `12` | the **cost factor**: how much work the scrambling took (section 3) |
| `Nt7kQx…` | the **salt** (first 22 characters) followed by the scrambled fingerprint |

The salt is stored right there in the same string, which is why the table needs no
separate column for it. The salt isn't a secret — it just has to be *different for
every password*, and section 3 explains why that matters so much.

## 3. What happens when you register

One small function does the work, at
[user_management.py:11-13](../BackEnd/src/user_management.py#L11-L13):

```python
def _hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt (cost factor 12)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
```

Three lines, but two important ideas are packed into them.

**The salt (`bcrypt.gensalt`).** Before scrambling, we generate a chunk of random
data and mix it into your password. A fresh, different one for every password we ever
hash.

Why bother? Without a salt, the same password always scrambles to the same result.
That's a gift to an attacker: they can pre-compute the fingerprints of the ten million
most common passwords once (a "rainbow table"), then match that list against a stolen
database and instantly crack every account using a common password. Worse, identical
fingerprints in the table would reveal which users share a password.

With a per-password salt, none of that works. Two people who both chose
`hunter2` end up with completely different stored values, a pre-computed table is
useless because the attacker didn't know your salt in advance, and cracking a thousand
accounts means doing the work a thousand separate times instead of once.

**The cost factor (`rounds=12`).** bcrypt is *deliberately slow*. The `12` means the
scrambling repeats about 2¹² — roughly four thousand — times before producing a result.

This sounds like a bug and is actually the whole point. For you, logging in once, it
costs a few hundred milliseconds you won't notice. For an attacker holding a stolen
database and trying to guess billions of candidate passwords, that same delay
multiplies into years or centuries of computer time. Slowness is the defence. A fast
algorithm would let them try billions of guesses per second; bcrypt at cost 12 drops
that to a few thousand.

The hashing happens once, inline in the `INSERT`, at
[user_management.py:79-82](../BackEnd/src/user_management.py#L79-L82):

```python
cursor.execute("""
    INSERT INTO users (id, username, email, password_hash, created_at)
    VALUES (?, ?, ?, ?, ?)
""", (user_id, request.username, request.email, _hash_password(request.password), request.created_at))
```

The plaintext password exists only as a local variable for the duration of that one
request. It is never written to disk and never logged.

## 4. What happens when you log in

Back to the question from section 1: if we don't know your password, how can we check
it?

We don't decrypt anything — we *can't*. Instead we take the password you just typed,
run it through the exact same scrambler using the salt from your stored record, and
compare the two fingerprints. Match means you typed the right password. That's the
whole trick: we never learn your password, we only ever confirm that a fresh scramble
matches the old one.

This has a consequence worth pointing out, because the code carries a comment
explaining it — [user_management.py:119-125](../BackEnd/src/user_management.py#L119-L125):

```python
# Find user by username; verification happens in Python since bcrypt
# hashes are salted and can't be matched with SQL '='.
cursor.execute("""
    SELECT id, password_hash
    FROM users
    WHERE username = ? AND is_active = 1
""", (request.username,))
```

A naive login would query `WHERE username = ? AND password_hash = ?`. That's
impossible here: every hash contains its own random salt, so we have to fetch the
stored hash *first* to learn the salt, then do the comparison in Python. The
comparison itself is one call, at
[user_management.py:15-17](../BackEnd/src/user_management.py#L15-L17):

```python
def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
```

`bcrypt.checkpw` reads the salt and cost factor out of the stored string, re-runs the
scramble on what you typed, and compares.

One more deliberate detail: whether the username doesn't exist
([:129-135](../BackEnd/src/user_management.py#L129-L135)) or the password was wrong
([:146-152](../BackEnd/src/user_management.py#L146-L152)), you get the *same* message —
`"Invalid username or password"`. That's not laziness. If the two cases gave different
answers, an attacker could feed in usernames and learn which accounts exist before
starting to guess passwords at all. Disabled accounts (`is_active = 0`) are
indistinguishable from non-existent ones for the same reason.

## 5. Where the code lives

Everything in one table, for anyone who wants to read the source directly:

| Concern | Location |
|---|---|
| Hashing a new password | [`_hash_password`](../BackEnd/src/user_management.py#L11-L13) — user_management.py:11-13 |
| Checking a password | [`_verify_password`](../BackEnd/src/user_management.py#L15-L17) — user_management.py:15-17 |
| The `users` table definition | [`init_users_table`](../BackEnd/src/user_management.py#L40-L58) — user_management.py:40-58 |
| Registration flow | [`register_user`](../BackEnd/src/user_management.py#L60-L110) — user_management.py:60-110 |
| Login flow | [`login_user`](../BackEnd/src/user_management.py#L112-L177) — user_management.py:112-177 |
| The HTTP endpoints | [main.py:414-428](../BackEnd/src/main.py#L414-L428) |

Supporting facts:

- The library is the [`bcrypt`](https://pypi.org/project/bcrypt/) package, pinned as
  `bcrypt>=5.0.0` in [BackEnd/pyproject.toml](../BackEnd/pyproject.toml#L8).
- Cost factor 12 is **hardcoded** — there's no environment variable or config file
  entry that changes it. Raising it means editing line 13.
- There is no "pepper" (a site-wide secret mixed in on top of the salt).
- Accounts live in `BackEnd/db/persistent_data.sqlite`. The per-user content databases
  under `db/users/` hold no credentials at all.
- Both endpoints are rate limited — 5 registrations per hour, 10 login attempts per
  minute ([main.py:415](../BackEnd/src/main.py#L415),
  [main.py:421](../BackEnd/src/main.py#L421)) — which further limits online guessing.
- `get_user_by_id()`
  ([user_management.py:179-209](../BackEnd/src/user_management.py#L179-L209))
  deliberately selects every column *except* `password_hash`, so the hash never leaves
  this module.

## 6. What this protects against — and what it doesn't

**It protects against a database leak.** If someone walks off with
`persistent_data.sqlite`, they get a list of usernames and 60-character strings. They
cannot log in as anyone, and they cannot recover anyone's password to try on their
email or bank. That's the main thing password hashing buys you, and it works.

**It does not make a weak password safe.** bcrypt slows guessing down; it doesn't stop
it. If your password is `password123`, an attacker will find it whether it took them a
second or a week — it's near the top of every guessing list. Hashing protects the
*unpredictable* password, not the obvious one.

Some honest gaps in the current implementation:

> **No strength or length rules.** `RegisterUserRequest.password` is an unconstrained
> string ([user_models.py](../BackEnd/src/user_models.py#L7)) — nothing rejects a
> one-character password. The registration form only checks that the two
> confirm-password boxes match.
>
> **No password change or reset flow.** There is currently no way for a user to change
> their password or recover a forgotten one. Nothing in the codebase ever rewrites
> `password_hash` after registration — the value written when the account is created is
> the value it keeps for life.

**The password does travel in plaintext to the API.** The Streamlit UI POSTs the raw
password to `/api/login-user`
([Web/src/main.py:95-127](../Web/src/main.py#L95-L127)) — that's unavoidable, since the
server has to see the password to hash it. Protecting that hop is TLS's job, which is
a deployment concern (see [deploy-k8s.md](./deploy-k8s.md)) and is not enforced by the
application code. Over plain HTTP, hashing at rest doesn't help you.

**Hashing is not the same as the encryption used elsewhere.** LLM API keys are
*encrypted* with Fernet ([llm-keys.md](./llm-keys.md),
[db_crypto.py](../BackEnd/src/db_crypto.py)) rather than
hashed, because the application genuinely needs to read them back to call the provider.
That's reversible by design. Passwords are hashed precisely because nothing should ever
need to read them back. Two different tools for two different jobs — don't confuse the
guarantees.
