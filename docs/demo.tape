# grantry demo. Re-render with:  vhs docs/demo.tape
# Runs real grantry commands that work offline, so the GIF stays honest.
Output docs/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1180
Set Height 720
Set Padding 20
Set Theme "Dracula"

Hide
Type "export PATH=$PWD/.venv/bin:$PATH" Enter
Type "export GRANTRY_HOME=$(mktemp -d)" Enter
Type "export GRANTRY_SSO_START_URL=https://acme.awsapps.com/start GRANTRY_SSO_REGION=us-east-1" Enter
Type "export AWS_CONFIG_FILE=$GRANTRY_HOME/aws-config AWS_SHARED_CREDENTIALS_FILE=$GRANTRY_HOME/aws-creds" Enter
Type "unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_PROFILE" Enter
Type "clear" Enter
Show

Type "grantry status" Sleep 700ms Enter
Sleep 2.5s

Type "grantry check --sandbox" Sleep 700ms Enter
Sleep 3s

Type "grantry completion zsh | head -7" Sleep 700ms Enter
Sleep 2.5s

Type "grantry --help" Sleep 700ms Enter
Sleep 3.5s
