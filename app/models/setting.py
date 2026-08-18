from app.extensions import db


class Setting(db.Model):
    """Key/value table used by the administration page.

    The value is stored as JSON (text) so it can hold plain strings as
    well as lists (e.g. available item types).
    """

    __tablename__ = "settings"

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"<Setting {self.key}>"
