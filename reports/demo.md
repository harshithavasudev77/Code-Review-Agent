# Checkout service · intentionally flawed demo

**Decision:** pending
**Review complete:** yes
**Human review required:** yes
**Provider / model:** Nebius Token Factory / `nvidia/Nemotron-3_5-Lightning`
**Run:** `fe2be3ad-2f4d-4210-a158-9086ee72e5ba` · 2026-11-09T06:18:09.045370+00:00
**Source:** Synthetic teaching sample; not upstream open-source code
**Elapsed:** 14.8s · **LLM requests:** 8 · **Tokens:** 17,698 input / 4,116 output

## Assessment

The codebase contains multiple validated security and correctness issues in checkout.py. Critical injection flaws affect find_customer (SQL injection via f-string) and export_receipt (shell command injection via f-string with shell=True). High-severity bugs include a mutable default argument in add_item that shares state across calls, and a path traversal risk in open_store where unvalidated paths are passed to sqlite3.connect. Medium-severity findings duplicate some of these issues with lower confidence scores. No specialist failures were reported, but the source scope is limited to the provided findings and specialist summaries.

critical: 2 · high: 3 · medium: 5 · low: 0 · info: 0

## Prioritized findings

### CR-001 · CRITICAL · SQL injection in find_customer via f-string interpolation

`checkout.py:8-9` · Agents: bugs, security · Confidence: 100%

The function constructs a SQL query by directly interpolating the user-controlled `name` parameter into an f-string. An unauthenticated caller can pass arbitrary SQL, bypassing authentication or exfiltrating data from the customers table.

**Source evidence**

````text
    query = f"SELECT id, email FROM customers WHERE name = '{name}'"
    return connection.execute(query).fetchall()
````

**Recommendation:** Use parameterized queries with placeholders: `query = "SELECT id, email FROM customers WHERE name = ?"` and pass `(name,)` as the second argument to `connection.execute()`.

**Suggested test:** Call `find_customer` with a name like `'; DROP TABLE customers; --` and verify the database is not corrupted; then test a legitimate name returns correct rows.

### CR-002 · CRITICAL · Shell command injection in export_receipt

`checkout.py:22-22` · Agents: security · Confidence: 100%

The `destination` argument is interpolated into a shell command with `shell=True`. An unauthenticated caller can inject arbitrary shell commands via metacharacters.

**Source evidence**

````text
    return subprocess.run(f"cp receipt.txt {destination}", shell=True, check=True)
````

**Recommendation:** Pass the command as a list without shell=True, e.g. subprocess.run(['cp', 'receipt.txt', destination]), and validate/whitelist the destination path.

**Suggested test:** Pass destination='receipt.txt; id' and verify the shell executes the injected command.

### CR-003 · HIGH · Mutable default argument shared across calls in add_item

`checkout.py:16-18` · Agents: bugs, security · Confidence: 100%

The default value `cart=[]` is evaluated once at function definition time. Each call without an explicit `cart` argument mutates the same shared list, causing items to accumulate unexpectedly across calls.

**Source evidence**

````text
def add_item(item, cart=[]):
    cart.append(item)
    return cart
````

**Recommendation:** Use `cart=None` as default and initialize a new list inside the function: `if cart is None: cart = []`.

**Suggested test:** Call `add_item('a')` then `add_item('b')` without providing `cart` and assert the returned lists are independent (each contains only its own item).

### CR-004 · HIGH · Unsafe shell execution in export_receipt with string interpolation

`checkout.py:21-22` · Agents: bugs · Confidence: 100%

The function runs `cp receipt.txt {destination}` via `subprocess.run` with `shell=True`. The `destination` parameter is user-controlled and interpolated directly into the shell command, enabling command injection. An unauthenticated caller can append arbitrary shell commands.

**Source evidence**

````text
def export_receipt(destination):
    return subprocess.run(f"cp receipt.txt {destination}", shell=True, check=True)
````

**Recommendation:** Avoid `shell=True`. Pass the command as a list: `subprocess.run(['cp', 'receipt.txt', destination], check=True)`. If `shell=True` is required, rigorously validate and sanitize `destination` against a whitelist.

**Suggested test:** Call `export_receipt` with `destination="/tmp/receipt.txt; rm -rf /"` and verify no command injection occurs; with the fix, the command should safely copy the file.

### CR-005 · HIGH · Path traversal risk in open_store

`checkout.py:25-26` · Agents: security · Confidence: 90%

The `path` argument is passed directly to `sqlite3.connect` without validation. An unauthenticated caller can supply a path traversal string (e.g., `../../etc/passwd`) to access or create a database outside the intended directory.

**Source evidence**

````text
def open_store(path):
    return sqlite3.connect(path)
````

**Recommendation:** Validate that the resolved path is within an allowed base directory (e.g., using os.path.realpath and a prefix check) before connecting.

**Suggested test:** Pass path='../../../etc/passwd' and verify the function either rejects the path or only connects to allowed locations.

### CR-006 · MEDIUM · SQL injection in find_customer

`checkout.py:7-9` · Agents: tests · Confidence: 100%

The name parameter is interpolated directly into the SQL string. An unauthenticated caller can supply arbitrary request values, enabling SQL injection that can read or modify the database.

**Source evidence**

````text
def find_customer(name, connection):
    query = f"SELECT id, email FROM customers WHERE name = '{name}'"
    return connection.execute(query).fetchall()
````

**Recommendation:** Use a parameterized query: query = 'SELECT id, email FROM customers WHERE name = ?' with connection.execute(query, (name,)).

**Suggested test:** def test_find_customer_sql_injection():    conn = sqlite3.connect(':memory:')    conn.execute('CREATE TABLE customers (id INTEGER, email TEXT)')    conn.execute('INSERT INTO customers VALUES (1, 'user@example.com')')    result = find_customer(''; DROP TABLE customers; --', conn)    # With parameterized queries the injected SQL is treated as data

### CR-007 · MEDIUM · Mutable default argument in add_item

`checkout.py:16-18` · Agents: tests · Confidence: 95%

The default argument cart=[] is a mutable list shared across all calls that do not supply a cart. Repeated calls without a cart argument accumulate items unexpectedly.

**Source evidence**

````text
def add_item(item, cart=[]):
    cart.append(item)
    return cart
````

**Recommendation:** Replace the mutable default with None and initialize a new list inside the function body.

**Suggested test:** def test_add_item_no_arg_isolated():    assert add_item('a') == ['a']    assert add_item('b') == ['b']    assert add_item('c') == ['c']

### CR-008 · MEDIUM · Shell injection in export_receipt

`checkout.py:21-22` · Agents: tests · Confidence: 90%

The destination argument is interpolated into a shell command with shell=True. An unauthenticated caller can inject arbitrary shell commands via the destination path.

**Source evidence**

````text
def export_receipt(destination):
    return subprocess.run(f"cp receipt.txt {destination}", shell=True, check=True)
````

**Recommendation:** Avoid shell=True and pass arguments as a list: subprocess.run(['cp', 'receipt.txt', destination], check=True). If shell is required, validate and sanitize destination strictly.

**Suggested test:** def test_export_receipt_shell_injection():    import tempfile, os    dest = '/tmp/evil; rm -rf /'    # The test should verify that passing a destructive path either fails safely or is rejected by validation before reaching subprocess.

### CR-009 · MEDIUM · open_store exposes database path without validation

`checkout.py:25-26` · Agents: bugs · Confidence: 90%

The function returns `sqlite3.connect(path)` with no validation of `path`. An caller can pass an arbitrary path, potentially overwriting or reading files outside intended directories (e.g., `open_store('/etc/passwd')` or a maliciously crafted SQLite file).

**Source evidence**

````text
def open_store(path):
    return sqlite3.connect(path)
````

**Recommendation:** Validate that `path` resides within an allowed directory (e.g., using `os.path.commonpath` or checking for path traversal patterns) before connecting. Consider restricting to a dedicated data directory.

**Suggested test:** Attempt `open_store` with a path outside the expected scope and confirm it either raises an error or is rejected by validation.

### CR-010 · MEDIUM · Test covers only average_order_value

`test_checkout.py:6-7` · Agents: tests · Confidence: 85%

The test inventory shows only one test exists. The other three production functions (find_customer, add_item, export_receipt) have no unit tests. Adding tests for the identified injection and mutable-default issues improves regression coverage.

**Source evidence**

````text
def test_average_order_value():
    assert average_order_value([10, 20]) == 15
````

**Recommendation:** Add unit tests for find_customer (parameterized query behavior), add_item (mutable default fix), and export_receipt (shell safety).

**Suggested test:** def test_add_item_mutable_default_fixed():    assert add_item('a') == ['a']    assert add_item('b') == ['b']

## Next steps

- Replace f-string SQL interpolation in find_customer with parameterized queries (CR-001/CR-006).
- Rewrite export_receipt to avoid shell=True and interpolated commands (CR-002/CR-004).
- Fix add_item mutable default by using None and initializing a new list (CR-003/CR-007).
- Add path validation in open_store before connecting to sqlite3 (CR-005/CR-009).
- Add unit tests for find_customer, add_item, and export_receipt to prevent regression (CR-010).

## Specialist results

- **bugs — completed:** Review of intentionally flawed checkout demo with multiple anti-patterns and bugs.
- **security — completed:** Review of intentionally flawed checkout demo with untrusted caller input.
- **tests — completed:** Review of the intentionally flawed checkout demo. Two production code issues and one test improvement identified. Coverage was not measured.

## Limitations

- Static review only: submitted code was not executed and test coverage was not measured.
- Findings are limited to the submitted source snapshot; dependencies and deployment were not audited.
- Source is an intentionally flawed teaching fixture; findings reflect real patterns but the code should never run in production.
- No execution environment was available; findings are based on static code analysis only.
- Source is an intentionally flawed teaching fixture; findings reflect real code patterns but may not represent production risk magnitude.
- No runtime execution was performed; static analysis only.
- Test suggestions are based on injecting known payloads; actual exploitability depends on runtime context.
- Mutable default and path traversal findings rely on inspection of parameter flow; no dynamic validation was possible.
- Source files are a synthetic teaching fixture; behavior may not reflect production-grade code.
- No tests were actually executed; confidence values are based on code inspection alone.
- The mutable-default and injection risks assume the functions are called as documented with unauthenticated request values.
- Coverage was not measured and tests were not executed; only submitted files were inspected.

## Source manifest

- `checkout.py`: 26 lines; SHA-256 `c78de9cf8d1cd7596a1fb206327de2a01ec17b7dd18d4301aebdad2750b15e80`
- `test_checkout.py`: 7 lines; SHA-256 `bc2c2c16b949dec7fc82edb9e1aa4aaee39c2e55a78fa32561b58180d7e9ef43`
