from __future__ import print_function

import os
import json
import random
import re
import subprocess
import requests
import shutil
import sys
import uuid

from datetime import date
from distutils.core import Command

import pip

from cookiecutter.main import cookiecutter


class app(Command):
    description = "Create a native application to wrap this project"

    user_options = [
        ('dir=', 'd',
         "Directory to put the project in"),
        ('formal-name=', None,
         "Formal name for the project"),
        ('class-name=', None,
         "Entry class name for the project"),
        ('organization-name=', None,
         "Name of the organization managing the project"),
        ('template=', None,
         "Template (or template repository URL) to use."),
        ('bundle', None,
         'Bundle identifier for the author organization - usually a reversed domain (e.g., "org.python")'),
        ('icon=', None,
         "Name of the icon file."),
        ('guid=', None,
         "GUID identifying the app."),
        ('secret-key=', None,
         "Secret key for the app."),
        ('splash=', None,
         "Name of the splash screen file."),
        ('app-requires', None,
         'List of platform-specific requirements for this app.'),
        ('support-pkg=', 's',
         'URL for the support package to use'),
        ('download-dir=', None,
         "Directory where the project support packages will be cached"),
        ('build', None,
         "Build the project after generating"),
        ('execute', None,
         "Run the application after building"),
        ('os-version=', None,
         "Set the device OS version. Currently only iOS supported (e.g., iOS 10.2)"),
        ('device=', None,
         "Set the device to run. Currently only iOS supported (e.g., iPhone 7 Plus)")
    ]

    def initialize_options(self):
        self.dir = None
        self.formal_name = None
        self.class_name = None
        self.organization_name = None
        self.template = None
        self.bundle = None
        self.icon = None
        self.splash = None
        self.app_requires = None
        self.support_pkg = None
        self.support_dir = None
        self.download_dir = None
        self.version_code = None
        self.guid = None
        self.secret_key = None
        self.build = False
        self.execute = False
        self.os_version = None
        self.device = None

    def finalize_options(self):
        if self.formal_name is None:
            self.formal_name = self.distribution.get_name().title()

        if self.class_name is None:
            CLASS_NAME_CHARS = re.compile('[^a-zA-Z]')
            self.class_name = CLASS_NAME_CHARS.sub('', self.formal_name.title())

        if self.organization_name is None:
            self.organization_name = self.distribution.get_author().title()

        if self.bundle is None:
            if self.distribution.get_author_email():
                domain = self.distribution.get_author_email().split('@')[-1]
            else:
                domain = 'org.python'
            self.bundle = '.'.join(reversed(domain.split('.')))

        if self.download_dir is None:
            self.download_dir = os.path.expanduser(os.path.join('~', '.briefcase'))

        # The Version Code is a pure-string, numerically sortable
        # version number.
        match = re.match('(?P<major>\d+)(\.(?P<minor>\d+)(\.(?P<revision>\d+))?)?', self.distribution.get_version())
        self.version_code = '%02d%02d%02d' % (
            int(match.groups()[0]) if match.groups()[0] else 0,
            int(match.groups()[2]) if match.groups()[2] else 0,
            int(match.groups()[4]) if match.groups()[4] else 0,
        )

        # The app's GUID (if not manually specified) is a namespace UUID
        # based on the URL for the app.
        if self.guid is None:
            self.guid = uuid.uuid3(uuid.NAMESPACE_URL, self.distribution.get_url())

        # The secret key is 40 characters of entropy
        if self.secret_key is None:
            self.secret_key = ''.join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(40))

        pip.utils.ensure_dir(self.download_dir)

        if self.execute:
            self.build = True

    def find_support_pkg(self):
        api_url = 'https://pybee.org/static/api/%s/releases.json' % self.support_project

        try:
            releases = requests.get(api_url).json()
        except requests.exceptions.RequestException:
            print()
            print("We had trouble connecting to Github to look for appropriate")
            print("support packages. This can happen when you have tried too many")
            print("times. If you are working on briefcase, please use the specified")
            print("--support-pkg flag for development.")
            return None

        candidates = []
        for release in releases:
            if release['tag_name'] and release['tag_name'].startswith("%s.%s-" % (sys.version_info.major, sys.version_info.minor)):
                for asset in release['assets']:
                    if asset['name'].endswith('.tar.gz') and self.platform in asset['name']:
                        candidates.append((release['created_at'], asset['browser_download_url']))

        try:
            return sorted(candidates, reverse=True)[0][1]
        except IndexError:
            return None

    @property
    def app_dir(self):
        return os.path.join(os.getcwd(), self.resource_dir, 'app')

    @property
    def app_packages_dir(self):
        return os.path.join(os.getcwd(), self.resource_dir, 'app_packages')

    @property
    def version(self):
        return self.distribution.get_version()

    def generate_app_template(self):
        print(" * Writing application template...")

        if self.template is None:
            template_path = os.path.expanduser('~/.cookiecutters/Python-%s-template' % self.platform)
            if os.path.exists(template_path):
                self.template = template_path
                self.git_pull(template_path)
            else:
                self.template = 'https://github.com/pybee/Python-%s-template.git' % self.platform
        print("Project template: %s" % self.template)
        cookiecutter(
            self.template,
            no_input=True,
            checkout='%s.%s' % (sys.version_info.major, sys.version_info.minor),
            extra_context={
                'app_name': self.distribution.get_name(),
                'formal_name': self.formal_name,
                'class_name': self.class_name,
                'organization_name': self.organization_name,
                'author': self.distribution.get_author(),
                'description': self.distribution.get_description(),
                'dir_name': self.dir,
                'bundle': self.bundle,
                'year': date.today().strftime('%Y'),
                'month': date.today().strftime('%B'),
                'version': self.version,
                'version_code': self.version_code,
                'guid': self.guid,
                'secret_key': self.secret_key,
            }
        )

    def git_pull(self, path):
        template_name = path.split('/')[-1]
        try:
            subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT, cwd=path)
            print('Template %s succesfully updated.' % template_name)
        except subprocess.CalledProcessError as pull_error:
            error_message = pull_error.output.decode('utf-8')
            if 'resolve host' in error_message:
                print('Unable to update template %s, using unpulled.' % template_name)
            print(error_message)

    def install_app_requirements(self):
        print(" * Installing requirements...")
        if self.distribution.install_requires:
            pip.main([
                    'install',
                    '--upgrade',
                    '--force-reinstall',
                    '--target=%s' % self.app_packages_dir
                ] + self.distribution.install_requires,
            )
        else:
            print("No requirements.")

    def install_platform_requirements(self):
        print(" * Installing plaform requirements...")
        if self.app_requires:
            pip.main([
                    'install',
                    '--upgrade',
                    '--force-reinstall',
                    '--target=%s' % self.app_packages_dir,
                ] + self.app_requires
            )
        else:
            print("No platform requirements.")

    def install_code(self):
        print(" * Installing project code...")
        pip.main([
                'install',
                '--upgrade',
                '--force-reinstall',
                '--no-dependencies',  # We just want the code, not the dependencies
                '--target=%s' % self.app_dir,
                '.'
            ])

    def install_resources(self):
        if self.icon:
            print(" * Adding icons...")
            self.install_icon()
        else:
            print(" * No icons defined - using default...")

        if self.splash:
            print(" * Adding splash screens...")
            self.install_splash()
        else:
            print(" * No splash screen defined...")

    def install_support_package(self):
        if self.support_pkg is None:
            print(" * Determining best support package...")
            self.support_pkg = self.find_support_pkg()

        if self.support_dir is None:
            self.support_dir = self.resource_dir

        if self.support_pkg:
            print(" * Installing support package...")
            print("Support package:", self.support_pkg)
            pip.download.unpack_url(
                pip.index.Link(self.support_pkg),
                os.path.join(os.getcwd(), self.support_dir),
                download_dir=self.download_dir,
            )
        else:
            print()
            print("No pre-built support package could be found for Python %s.%s." % (sys.version_info.major, sys.version_info.minor))
            print("You will need to compile your own. You may want to start with")
            print("the code from https://github.com/%s and" % self.support_project)
            print("then specify the compiled tarball with:")
            print()
            print("    python setup.py %s --support-pkg=<path to tarball>" % self.platform.lower())
            print()

    def install_extras(self):
        pass

    def build_app(self):
        pass

    def run_app(self):
        pass

    def post_run(self):
        print()
        print("Installation complete.")

    def run(self):
        if os.path.exists(self.dir):
            print()
            if os.path.isdir(self.dir):
                confirm = input("A directory named '%s' already exists. Would you like to replace it (y/N)? " % self.dir)
            else:
                confirm = input("A file named '%s' already exists. Would you like to delete it (y/N)? " % self.dir)

            print()
            if confirm in ['y', 'Y']:
                print(" * Deleting existing content...")
                if os.path.isdir(self.dir):
                    shutil.rmtree(self.dir)
                else:
                    os.remove(self.dir)
            else:
                print("Briefcase deployment cancelled.")
                return

        self.generate_app_template()
        self.install_app_requirements()
        self.install_platform_requirements()
        self.install_code()
        self.install_resources()
        self.install_support_package()
        self.install_extras()

        if self.build:
            self.build_app()
        if self.execute:
            self.run_app()

        self.post_run()
