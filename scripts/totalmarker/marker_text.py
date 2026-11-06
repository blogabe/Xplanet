"""Quoted Xplanet marker labels: its parser does not implement backslash escapes."""

def quoted_label(value):
    # Normalize provider text before quoting; a quote must never terminate a label.
    text=''.join(char if char.isprintable() else ' ' for char in str(value))
    return '"'+text.replace('"', "'").replace('\\', '/')+'"'
