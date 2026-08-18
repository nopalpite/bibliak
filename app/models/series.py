from app.extensions import db

# Number of spine tones available in the palette (see layout.html,
# classes .spine-1 to .spine-SPINE_COLOR_COUNT).
SPINE_COLOR_COUNT = 8


class Series(db.Model):
    __tablename__ = "series"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    expected_volume_count = db.Column(db.Integer, nullable=True)

    @property
    def spine_color_class(self):
        """CSS class for this series' spine color.

        Deterministic (based on id) rather than picked at random on every
        render: a given series always keeps the same color.
        """
        return f"spine-{(self.id % SPINE_COLOR_COUNT) + 1}"

    def __repr__(self):
        return f"<Series {self.name}>"
