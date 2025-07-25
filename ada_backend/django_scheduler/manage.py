#!/usr/bin/env python
import os
import sys
import django


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ada_backend.django_scheduler.django_settings")
    django.setup()

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
