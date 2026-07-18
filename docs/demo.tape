# grantry demo. Re-render with:  vhs docs/demo.tape
# Runs real grantry commands that work offline, so the GIF stays honest.
# (A small identity cache is pre-seeded at $GRANTRY_HOME so TAB completion has
# something to complete; see the render command that writes it.)
Output docs/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1180
Set Height 720
Set Padding 20
Set Theme "Dracula"

Hide
Type "export PATH=$PWD/.venv/bin:$PATH" Enter
Type "export GRANTRY_HOME=/tmp/grantry-demo" Enter
Type "export GRANTRY_SSO_START_URL=https://acme.awsapps.com/start GRANTRY_SSO_REGION=us-east-1" Enter
Type "export AWS_CONFIG_FILE=$GRANTRY_HOME/aws-config AWS_SHARED_CREDENTIALS_FILE=$GRANTRY_HOME/aws-creds" Enter
Type "unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_PROFILE" Enter
Type "grantry completion bash > /tmp/gc.bash && source /tmp/gc.bash" Enter
Type "bind 'set show-all-if-ambiguous on'" Enter
Type "clear" Enter
Show

Type "grantry status" Sleep 700ms Enter
Sleep 2.2s

Type "grantry check --sandbox" Sleep 700ms Enter
Sleep 2.5s

Type "# TAB completes your real account.role identities" Sleep 400ms Enter
Type "grantry switch acme-pa" Sleep 900ms
Tab Sleep 2200ms
Ctrl+C Sleep 700ms

Type "grantry --help" Sleep 700ms Enter
Sleep 3s
