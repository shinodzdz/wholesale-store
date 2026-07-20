from app import app, Admin, db
import hashlib

with app.app_context():
    admin = Admin.query.filter_by(username='admin').first()
    if not admin:
        print('❌ حساب المدير غير موجود.')
        exit(1)

    new_pass = input('أدخل كلمة السر الجديدة للمدير: ').strip()
    if len(new_pass) < 4:
        print('❌ كلمة السر يجب أن تكون 4 أحرف على الأقل.')
        exit(1)

    admin.password = hashlib.sha256(new_pass.encode()).hexdigest()
    db.session.commit()
    print(f'✅ تم تغيير كلمة سر المدير إلى: {new_pass}')
