# Deploying Quantum Bank Bot to Heroku

This guide explains how to deploy the Quantum Bank Discord bot to Heroku using the GitHub Actions workflow included in this repository.

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
```

### 4. Deploy Using GitHub Actions

The deployment workflow will trigger automatically when you push to the `main` branch. You can also trigger it manually:

1. Go to your repository on GitHub
2. Navigate to Actions
3. Select "Deploy to Heroku" workflow
4. Click "Run workflow"
5. Choose "main" branch and "production" environment
6. Click "Run workflow"

### 5. Monitor the Deployment

You can monitor the deployment in:

- GitHub Actions tab to see the workflow progress
- Heroku dashboard to see the app status
- Heroku logs for detailed logging information:

```bash
heroku logs --tail -a your-app-name
```

## Health Checks

The bot includes a health check endpoint at `/health` that returns a 200 OK response when the bot is running correctly. The GitHub Actions workflow uses this endpoint to verify that the deployment was successful.

## Troubleshooting

### Common Issues

1. **Deployment Fails**: Check the GitHub Actions logs for specific error messages.
2. **Bot Crashes on Startup**: Check the Heroku logs with `heroku logs --tail -a your-app-name`.
3. **Bot Connects but Commands Don't Work**: Verify that all required environment variables are set correctly.

### Checking Logs

```bash
# View recent logs
heroku logs -a your-app-name

# Stream logs in real-time
heroku logs --tail -a your-app-name
```

## Scaling

You can scale your bot's dynos using the Heroku CLI:

```bash
# Scale to 1 worker dyno
heroku ps:scale worker=1 -a your-app-name
```

## Additional Resources

- [Heroku DevCenter](https://devcenter.heroku.com/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions) 