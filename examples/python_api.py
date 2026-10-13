from moodlectl import BrowserMoodle, ResourceSpec
from moodlectl.config import Settings

config = Settings.load(site="https://virtuale.unibo.it")
with BrowserMoodle(config) as moodle:
    print(moodle.course_sections(80509))
    print(moodle.list_resources(80509, "Module 2"))

    spec = ResourceSpec(
        kind="url",
        name="A demo lecture",
        url="https://example.org/lecture.pdf",
        description="[Rolling slides](https://example.org/lecture/)",
        description_format="markdown",
        show_description=True,
        visible=False,
        fields={"#id_display": {"label": "Open"}},
    )
    # Uncomment to write to Moodle:
    # print(moodle.add_resource(80509, "Module 2", spec))
