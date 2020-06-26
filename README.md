# Xplanet

Xplanet on Mac
https://blog.rajab.us/xplanet/

To install:
```
cd ~
git clone https://github.com/blogabe/Xplanet.git ~/.xplanet
cd ~/.xplanet/config/scripts
./xplanet.sh install
./xplanet.sh setup
exit                                    # After the script completes then open a new terminal for the changes
```

To update (this will overwrite whatever changes you have made):
```
git -C "$HOME/.xplanet" pull origin master'
exit                                    # After the script completes then open a new terminal for the changes
```
