import sqlite3, hashlib, os

db_path = os.path.join(os.path.dirname(__file__), 'database.db')
if not os.path.exists(db_path):
    print('❌ ملف قاعدة البيانات غير موجود.')
    exit(1)

conn = sqlite3.connect(db_path)
admin = conn.execute('SELECT * FROM admins WHERE username=?', ('admin',)).fetchone()
if not admin:
    print('❌ حساب المدير غير موجود.')
    exit(1)

new_pass = input('أدخل كلمة السر الجديدة للمدير: ').strip()
if len(new_pass) < 4:
    print('❌ كلمة السر يجب أن تكون 4 أحرف على الأقل.')
    exit(1)

conn.execute('UPDATE admins SET password=? WHERE username=?',
             (hashlib.sha256(new_pass.encode()).hexdigest(), 'admin'))
conn.commit()
conn.close()
print(f'✅ تم تغيير كلمة سر المدير إلى: {new_pass}')
