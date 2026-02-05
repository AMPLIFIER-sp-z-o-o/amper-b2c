
## 🏢 About

**AMPER-B2C** is a top-notch, next-gen B2C e-commerce solution.

**AMPER B2C** is developed and maintained by **AMPLIFIER sp. z o.o.**, a software company specializing in B2B/B2C e-commerce platforms, mobile applications (SFA/FSM), and enterprise integrations.

This project is part of the **AMPER ecosystem** used in real production environments by manufacturers, distributors, and retail networks.

## 🌐 Live Demo

You can see AMPER B2C in action on our public demo environment.

> Demo URL: **https://amper-b2c.ampliapps.com/**  
> Login: **admin@example.com**  
> Password: **admin**

The demo presents typical B2C storefront features, admin panel, customer flows, and integrations used in real deployments.

## 🤝 Support & Cooperation

This is an **actively maintained** project.

We offer:

- Production deployments
- Custom development
- ERP / WMS / PIM integrations
- Performance tuning
- Mobile app integrations
- DevOps & hosting support

If you plan to use AMPER B2C commercially, go ahead - it's under MIT license. You can do it independently, **or** we are ready to help.

## 📬 Contact

- 🌍 https://ampliapps.com  
- 📧 support@ampliapps.com

## 🚀 Project Status

- Production-ready
- Actively developed
- Used by real customers
- Backed by a professional engineering team
- Long-term supported

## ❤️ Contributing

Issues, ideas, and pull requests are welcome.

For larger changes, please open an issue first to align with the roadmap.

## Default Credentials

After running `make seed`, the following superuser is available:

| Field    | Value             |
| -------- | ----------------- |
| Email    | admin@example.com |
| Password | admin             |

## Quickstart

### Prerequisites

To run the app in the recommended configuration, you will need the following installed:

- [Docker](https://www.docker.com/get-started) and [Docker Compose](https://docs.docker.com/compose/install)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (for Python)
- [node and npm](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) (for JavaScript)

On Windows, you will also need to install `make`, which you can do by
[following these instructions](https://stackoverflow.com/a/57042516/8207).

### Initial setup

Run the following command to initialize your application:

```bash
make init
```

This will:

- Build and run your Postgres database
- Build and run your Redis database
- Run your database migrations
- Install front end dependencies

Then you can start the app:

```bash
make dev
```

This will run your Django server and build and run your front end (JavaScript and CSS) pipeline.

Your app should now be running! You can open it at [localhost:8000](http://localhost:8000/).

## Using the Makefile

You can run `make` to see other helper functions, and you can view the source
of the file in case you need to run any specific commands.

## Installation - Native

You can also install/run the app directly on your OS using the instructions below.

You can setup a virtual environment and install dependencies in a single command with:

```bash
uv sync
```

This will create your virtual environment in the `.venv` directory of your project root.

## Set up database

_If you are using Docker you can skip these steps._

Create a database named `amplifier`.

```
createdb amplifier
```

Create database migrations:

```
uv run manage.py makemigrations
```

Create database tables:

```
uv run manage.py migrate
```

## Running server

```bash
uv run manage.py runserver
```

## Building front-end

To build JavaScript and CSS files, first install npm packages:

```bash
npm install
```

Then build (and watch for changes locally):

```bash
npm run dev
```

## Running Celery

Celery can be used to run background tasks.

Celery requires [Redis](https://redis.io/) as a message broker, so make sure
it is installed and running.

You can run it using:

```bash
celery -A amplifier worker -l INFO --pool=solo
```

Or with celery beat (for scheduled tasks):

```bash
celery -A amplifier worker -l INFO -B --pool=solo
```

Note: Using the `solo` pool is recommended for development but not for production.

## Updating translations

**Using make:**

```bash
make translations
```

**Native:**

```bash
uv run manage.py makemessages --all --ignore node_modules --ignore .venv
uv run manage.py makemessages -d djangojs --all --ignore node_modules --ignore .venv
uv run manage.py compilemessages --ignore .venv
```

## Google Authentication Setup

To setup Google Authentication, follow the [instructions here](https://docs.allauth.org/en/latest/socialaccount/providers/google.html).

## Twitter Authentication Setup

To setup Twitter Authentication, follow the [instructions here](https://docs.allauth.org/en/latest/socialaccount/providers/twitter_oauth2.html).

## Installing Git commit hooks

To install the Git commit hooks run the following:

```shell
uv run pre-commit install --install-hooks
```

Once these are installed they will be run on every commit.

## Running Tests

To run tests:

**Using make:**

```bash
make test
```

**Native:**

```bash
uv run manage.py test
```

Or to test a specific app/module:

**Using make:**

```bash
make test ARGS='apps.web.tests.test_basic_views --keepdb'
```

**Native:**

```bash
uv run manage.py test apps.web.tests.test_basic_views --keepdb
```

On Linux-based systems you can watch for changes using the following:

```bash
find . -name '*.py' | entr uv run manage.py test apps.web.tests.test_basic_views
```
