# # import os
# # import sys


# # sys.path.insert(0, os.path.dirname(__file__))


# # def application(environ, start_response):
# #     start_response('200 OK', [('Content-Type', 'text/plain')])
# #     message = 'It works!\n'
# #     version = 'Python %s\n' % sys.version.split()[0]
# #     response = '\n'.join([message, version])
# #     return [response.encode()]



# import sys
# import os
# from django.core.wsgi import get_wsgi_application

# # Add your project directory to the sys.path
# sys.path.append('/home/odayscom/src')  # Change to your project directory

# # Set the DJANGO_SETTINGS_MODULE environment variable
# os.environ['DJANGO_SETTINGS_MODULE'] = 'project.settings'

# # Create the WSGI application
# application = get_wsgi_application()
