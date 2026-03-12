#!/usr/bin/env python3
"""
Staging Agent - Docker deployment and review
"""

import subprocess
import sys
import time
from pathlib import Path

CONTAINER_NAME = "gironimo-staging"
IMAGE_NAME = "gironimo-staging:latest"


def build():
    """Build Docker image"""
    if not Path("Dockerfile").exists():
        print("No Dockerfile found. Generating...")
        generate_dockerfile()
    
    print("Building Docker image...")
    result = subprocess.run(
        ['docker', 'build', '-t', IMAGE_NAME, '.'],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Build failed: {result.stderr}")
        return False
    
    print(f"Built: {IMAGE_NAME}")
    return True


def deploy():
    """Run container"""
    stop()
    
    # Detect ports
    ports = detect_ports()
    port_args = []
    for p in ports:
        port_args.extend(['-p', f"{p}:{p}"])
    
    cmd = ['docker', 'run', '-d', '--name', CONTAINER_NAME] + port_args + [IMAGE_NAME]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Deploy failed: {result.stderr}")
        return False
    
    print(f"Deployed: {CONTAINER_NAME}")
    print(f"Ports: {', '.join(ports)}")
    
    # Wait for health
    print("Waiting for service...", end="", flush=True)
    for i in range(30):
        time.sleep(1)
        if is_healthy():
            print(" ✓")
            return True
        print(".", end="", flush=True)
    
    print("\nTimeout waiting for service")
    return False


def stop():
    """Stop and remove container"""
    subprocess.run(['docker', 'stop', CONTAINER_NAME], capture_output=True)
    subprocess.run(['docker', 'rm', CONTAINER_NAME], capture_output=True)


def logs():
    """Show container logs"""
    result = subprocess.run(
        ['docker', 'logs', CONTAINER_NAME, '--tail', '50'],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    return result.stdout


def is_healthy():
    """Check if container is responding"""
    result = subprocess.run(
        ['docker', 'ps', '--filter', f'name={CONTAINER_NAME}', '--filter', 'health=healthy', '-q'],
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())


def generate_dockerfile():
    """Generate Dockerfile based on project type"""
    if Path("package.json").exists():
        dockerfile = """FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["npm", "start"]"""
    elif Path("requirements.txt").exists():
        dockerfile = """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "app.py"]"""
    elif Path("go.mod").exists():
        dockerfile = """FROM golang:1.21-alpine
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o app .
EXPOSE 8080
CMD ["./app"]"""
    else:
        dockerfile = """FROM alpine:latest
WORKDIR /app
COPY . .
EXPOSE 3000
CMD ["echo", "No Dockerfile template for this project type"]"""
    
    Path("Dockerfile").write_text(dockerfile)
    print("Generated Dockerfile")


def detect_ports():
    """Detect exposed ports from Dockerfile"""
    if Path("Dockerfile").exists():
        content = Path("Dockerfile").read_text()
        import re
        ports = re.findall(r'EXPOSE\s+(\d+)', content)
        if ports:
            return ports
    return ["3000", "8000"]  # Defaults


def take_screenshots():
    """Take screenshots of running app"""
    ports = detect_ports()
    main_port = ports[0]
    
    urls = [
        f"http://localhost:{main_port}/",
        f"http://localhost:{main_port}/login",
    ]
    
    screenshots = []
    for url in urls[:2]:  # Limit to 2 URLs
        path = f"staging_{url.replace('/', '_').replace(':', '').replace('http', '')}.png"
        cmd = f"npx playwright screenshot --viewport-size=1280,720 {url} {path}"
        subprocess.run(cmd, shell=True, capture_output=True)
        
        if Path(path).exists():
            screenshots.append((url, path))
            print(f"  Screenshot: {path}")
    
    return screenshots


def run_api_tests():
    """Test API endpoints"""
    ports = detect_ports()
    main_port = ports[0]
    
    endpoints = [
        ("GET", "/health"),
        ("GET", "/status"),
        ("GET", "/api/health"),
    ]
    
    results = []
    for method, path in endpoints:
        url = f"http://localhost:{main_port}{path}"
        try:
            import urllib.request
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=2) as resp:
                status = resp.status
                ok = 200 <= status < 300
                results.append((method, path, status, "✓" if ok else "✗"))
        except Exception as e:
            results.append((method, path, str(e), "✗"))
    
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: staging.py [--build|--deploy|--stop|--logs|--review]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "--build":
        sys.exit(0 if build() else 1)
    
    elif cmd == "--deploy":
        sys.exit(0 if deploy() else 1)
    
    elif cmd == "--stop":
        stop()
    
    elif cmd == "--logs":
        print(logs())
    
    elif cmd == "--review":
        # Build and deploy
        if not build():
            sys.exit(1)
        if not deploy():
            sys.exit(1)
        
        print("\n📸 Taking screenshots...")
        screenshots = take_screenshots()
        
        print("\n🔍 Testing API...")
        api_results = run_api_tests()
        for method, path, status, ok in api_results:
            print(f"  {ok} {method} {path}: {status}")
        
        print(f"\n🌐 Staging URL: http://localhost:{detect_ports()[0]}")
        print("Logs: docker logs gironimo-staging")
        
        # Human review
        print("\n" + "=" * 50)
        print("Review complete. Approve?")
        response = input("[y/n]: ").lower().strip()
        
        if response == 'y':
            print("Staging approved")
            sys.exit(0)
        else:
            print("Staging rejected")
            sys.exit(1)
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
