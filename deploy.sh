#!/bin/bash
# Deploy Bort Search to DigitalOcean droplet
set -e

SSH_KEY="$HOME/.ssh/id_rsa_do"
SERVER="root@167.172.21.29"
SSH_OPTS="-i $SSH_KEY"
APP_DIR="/opt/bort"

echo "=== Step 1: Installing Docker on server ==="
ssh $SSH_OPTS $SERVER 'bash -s' << 'REMOTE'
apt-get update
apt-get install -y docker.io docker-compose-v2
systemctl enable docker
systemctl start docker
mkdir -p /opt/bort/data
REMOTE

echo "=== Step 2: Copying app code ==="
rsync -avz -e "ssh $SSH_OPTS" --exclude='data/' --exclude='venv/' --exclude='__pycache__/' \
  --exclude='.git/' --exclude='training/' --exclude='models/' \
  ./ $SERVER:$APP_DIR/

echo "=== Step 3: Copying database ==="
echo "This may take a while (~500MB)..."
rsync -avz -e "ssh $SSH_OPTS" --progress data/simpsons.lance/ $SERVER:$APP_DIR/data/simpsons.lance/

echo "=== Step 4: Creating .env file ==="
ssh $SSH_OPTS $SERVER "cat > $APP_DIR/.env << 'EOF'
DATABASE_PATH=data/simpsons.lance
FRAMES_PATH=data/frames
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=*
IMAGE_CDN_URL=https://pub-ddca3bee9c6a4ab39aa9ce0d03e8190a.r2.dev
EOF"

echo "=== Step 5: Building and starting container ==="
ssh $SSH_OPTS $SERVER "cd $APP_DIR && docker compose up -d --build"

echo ""
echo "=== Done! ==="
echo "Visit: http://167.172.21.29:8000"
echo ""
echo "To check logs: ssh $SSH_OPTS $SERVER 'cd $APP_DIR && docker compose logs -f'"
