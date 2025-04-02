# Deploying Quantum Bank Bot to Heroku

This guide explains how to deploy the Quantum Bank Discord bot to Heroku using the GitHub Actions workflows included in this repository.

## Branch Strategy Overview

The project uses the following branch strategy for deployments:

1. **Feature Branches** (`feature/*`): For developing new features
2. **Build Pipelines Branch** (`build-pipelines`): For staging deployment and validation
3. **Heroku Deployment Branch** (`heroku-deployment`): For production deployment to Heroku

## Prerequisites

1. A [Heroku](https://heroku.com) account
2. [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) installed locally
3. Your bot code in a GitHub repository
4. Administrator access to the GitHub repository

## Setup Steps

### 1. Create a Heroku App

```bash
# Login to Heroku
heroku login

# Create a new Heroku app
heroku create quantum-bank-bot

# Or if you want a specific name:
heroku create your-app-name
```

### 2. Configure GitHub Secrets

Add the following secrets to your GitHub repository:

1. Go to your repository on GitHub
2. Navigate to Settings > Secrets and variables > Actions
3. Add the following secrets:
   - `HEROKU_API_KEY`: Your Heroku API key (find it in your Heroku account settings)
   - `HEROKU_APP_NAME`: The name of your Heroku app
   - `HEROKU_EMAIL`: The email address associated with your Heroku account

### 3. Configure Environment Variables in Heroku

Set the required environment variables for your bot:

```bash
# Set Discord bot token
heroku config:set BOT_TOKEN=your_discord_bot_token -a your-app-name

# Set MongoDB URI (if using MongoDB)
heroku config:set MONGO_URI=your_mongodb_uri -a your-app-name

# Set other required environment variables
heroku config:set MAL_CLIENT_ID=your_mal_client_id -a your-app-name

# Set additional optional variables
heroku config:set PERFORMANCE_MODE=medium -a your-app-name
heroku config:set ACTIVITY_STATUS="Quantum Bank | /help" -a your-app-name
```

### 4. Deploy Using GitHub Actions

The deployment workflow follows this process:

1. **Feature Development**:
   - Develop features in `feature/*` branches
   - Push to trigger integration tests

2. **Staging Deployment**:
   - Merge feature branches to `build-pipelines`
   - This triggers the staging deployment workflow
   - Changes are deployed to staging and validated

3. **Production Deployment**:
   - Create/update a PR from `build-pipelines` to `heroku-deployment`
   - After validation, merge the PR
   - This triggers the Heroku deployment workflow
   - Your bot is deployed to production

You can also trigger the workflow manually:

1. Go to your repository on GitHub
2. Navigate to Actions
3. Select "Deploy to Heroku" workflow
4. Click "Run workflow"
5. Choose the appropriate branch
6. Click "Run workflow"

### 5. Monitor the Deployment

You can monitor the deployment in:

- GitHub Actions tab to see the workflow progress
- Heroku dashboard to see the app status
- Heroku logs for detailed logging information:

```bash
heroku logs --tail -a your-app-name
```

## Health Checks and Monitoring

The bot includes several endpoints for monitoring:

- `/health` - Returns a 200 OK response when the bot is running correctly
- `/status` - Returns detailed status information in JSON format including uptime, guild count, etc.

You can access these endpoints at:
```
https://your-app-name.herokuapp.com/health
https://your-app-name.herokuapp.com/status
```

## Scaling

Quantum Bank Bot uses both web and worker dynos:
- **Web dyno**: Handles HTTP requests including health checks
- **Worker dyno**: Runs the actual Discord bot functionality

You can scale your bot's dynos using the Heroku CLI:

```bash
# Scale to 1 web and 1 worker dyno (recommended)
heroku ps:scale web=1 worker=1 -a your-app-name

# For hobby/free tier, use only worker:
heroku ps:scale web=0 worker=1 -a your-app-name
```

## Advanced Configuration

### Using Custom Domain

```bash
# Add your custom domain
heroku domains:add bot.yourdomain.com -a your-app-name

# Follow the DNS instructions provided by Heroku
```

### Using Heroku Metrics

Heroku provides metrics for your application. To view metrics:

1. Go to your Heroku dashboard
2. Select your application
3. Click on the "Metrics" tab

### Continuous Deployment

The GitHub Action workflow in `.github/workflows/heroku-deploy.yml` automatically deploys your bot whenever you push to the `heroku-deployment` branch.

## Canary Deployments

For more controlled rollouts, we support canary deployments:

1. Use the staging workflow with canary option:
   ```bash
   gh workflow run staging-deploy.yml -f deploy_type=canary
   ```

2. Or use the production workflow with percentage control:
   ```bash
   gh workflow run production-deploy.yml -f deploy_percentage=20
   ```

See [CANARY_DEPLOYMENT.md](CANARY_DEPLOYMENT.md) for detailed information.

## Troubleshooting

### Common Issues

1. **Deployment Fails**: Check the GitHub Actions logs for specific error messages.
2. **Bot Crashes on Startup**: Check the Heroku logs with `heroku logs --tail -a your-app-name`.
3. **Bot Connects but Commands Don't Work**: Verify that all required environment variables are set correctly.
4. **H10 - App Crashed**: This usually means the bot crashed. Check the logs for the reason.
5. **R14 - Memory Quota Exceeded**: Your bot is using too much memory. Consider optimizing or upgrading your dyno.

### Checking Logs

```bash
# View recent logs
heroku logs -a your-app-name

# Stream logs in real-time
heroku logs --tail -a your-app-name
```

### Restarting the Bot

If the bot is experiencing issues, you can restart it:

```bash
heroku dyno:restart -a your-app-name
```

## Additional Resources

- [Heroku DevCenter](https://devcenter.heroku.com/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Heroku Container Registry](https://devcenter.heroku.com/articles/container-registry-and-runtime) 