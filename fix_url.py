import os
import django
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
django.setup()

from django.conf import settings

# التطبيقات اللي هنعمل لها تعديل
APPS = {
    app: []
    for app in settings.INSTALLED_APPS
    if not app.startswith("django.contrib")
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


def get_app_urls():
    """جلب أسماء الـ URLs من ملفات urls.py لكل تطبيق"""
    for app in list(APPS.keys()):
        try:
            module = __import__(f"{app}.urls", fromlist=['urlpatterns'])
            urlpatterns = getattr(module, 'urlpatterns', [])
            url_names = []
            for url in urlpatterns:
                if hasattr(url, 'name') and url.name:
                    url_names.append(url.name)
                elif hasattr(url, 'url_patterns'):
                    for sub_url in url.url_patterns:
                        if hasattr(sub_url, 'name') and sub_url.name:
                            url_names.append(sub_url.name)
            APPS[app] = url_names
        except Exception:
            del APPS[app]


def fix_views(app):
    """تعديل redirect في ملفات views.py"""
    views_path = os.path.join(BASE_DIR, app, "views.py")
    if not os.path.exists(views_path):
        return
    try:
        with open(views_path, "r", encoding="utf-8") as f:
            content = f.read()
        changed = False
        for view in APPS.get(app, []):
            pattern = rf"redirect\s*\(\s*['\"]{view}['\"]\s*\)"
            replacement = f"redirect('{app}:{view}')"
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                print(f"✅ عدلت redirect('{view}') → redirect('{app}:{view}') في {views_path}")
                changed = True
        if changed:
            with open(views_path, "w", encoding="utf-8") as f:
                f.write(content)
    except Exception as e:
        print(f"⚠️ خطأ في تعديل {views_path}: {e}")


def fix_templates():
    """تعديل {% url 'view' %} في القوالب"""
    if not os.path.exists(TEMPLATES_DIR):
        return
    for root, _, files in os.walk(TEMPLATES_DIR):
        for file in files:
            if file.endswith(".html"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    changed = False
                    for app, views in APPS.items():
                        for view in views:
                            pattern = rf"\{{%\s*url\s+['\"]{view}['\"]\s*%}}"
                            replacement = f"{{% url '{app}:{view}' %}}"
                            if re.search(pattern, content):
                                content = re.sub(pattern, replacement, content)
                                print(f"✅ عدلت {{% url '{view}' %}} → {{% url '{app}:{view}' %}} في {file_path}")
                                changed = True
                    if changed:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(content)
                except Exception as e:
                    print(f"⚠️ خطأ أثناء تعديل {file_path}: {e}")


def main():
    get_app_urls()
    for app in APPS:
        fix_views(app)
    fix_templates()
    print("✅ تم تعديل كل الملفات")


if __name__ == "__main__":
    main()
