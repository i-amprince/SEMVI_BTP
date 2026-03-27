import subprocess

def run(cmd):
    subprocess.run(cmd, shell=True)

print("Stopping all containers...")
run("for /f %i in ('docker ps -aq') do docker stop %i")

print("Removing all containers...")
run("for /f %i in ('docker ps -aq') do docker rm -f %i")

print("Removing all images...")
run("for /f %i in ('docker images -aq') do docker rmi -f %i")

print("Removing all volumes...")
run("for /f %i in ('docker volume ls -q') do docker volume rm %i")

print("Removing all networks...")
run("for /f %i in ('docker network ls -q') do docker network rm %i")

print("Final prune...")
run("docker system prune -a -f --volumes")

print("Docker fully cleaned.")
