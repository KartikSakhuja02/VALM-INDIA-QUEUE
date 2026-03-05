# PostgreSQL Setup for Raspberry Pi

## Installation Steps

Run these commands on your Raspberry Pi:

```bash
# Update package list
sudo apt update

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# Check PostgreSQL service status
sudo systemctl status postgresql

# If not running, start it
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

## Database Setup

```bash
# Switch to postgres user
sudo -u postgres psql

# Inside PostgreSQL prompt, create database and user:
CREATE DATABASE valmindiaqueue;
CREATE USER valmbot WITH PASSWORD 'your_secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE valmindiaqueue TO valmbot;
\c valmindiaqueue
GRANT ALL ON SCHEMA public TO valmbot;
\q

# Exit postgres user
exit
```

## Connection Test

```bash
# Test connection with the new user
psql -U valmbot -d valmindiaqueue -h localhost

# Inside psql:
\dt  # List tables (will be empty initially)
\q   # Quit
```

## Configure PostgreSQL for Local Connections

If you get authentication errors, edit the pg_hba.conf file:

```bash
# Find the config file location (to check your PostgreSQL version)
sudo -u postgres psql -c "SHOW hba_file;"

# Or find all pg_hba.conf files
sudo find /etc/postgresql -name pg_hba.conf

# Edit the file with your PostgreSQL version (check output above)
# For PostgreSQL 17:
sudo nano /etc/postgresql/17/main/pg_hba.conf
# For PostgreSQL 15:
# sudo nano /etc/postgresql/15/main/pg_hba.conf

# Change the line:
# local   all             all                                     peer
# TO:
# local   all             all                                     md5

# Also change:
# host    all             all             127.0.0.1/32            ident
# TO:
# host    all             all             127.0.0.1/32            md5

# Save and restart PostgreSQL
sudo systemctl restart postgresql
```

## Update .env File

Add to your `.env` file:

```
DATABASE_URL=postgresql://valmbot:your_secure_password_here@localhost/valmindiaqueue
```

Replace `your_secure_password_here` with the password you set above.

## Verify Setup

```bash
# Check if PostgreSQL is listening
sudo netstat -plunt | grep postgres

# Or use ss:
sudo ss -plunt | grep postgres
```
