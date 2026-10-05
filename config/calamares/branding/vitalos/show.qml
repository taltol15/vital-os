import QtQuick 2.5

Rectangle {
    id: root
    color: "#0E1116"
    anchors.fill: parent

    property int slide: 0
    property var titles: [
        "Nocturne",
        "A quiet desktop",
        "Vital Marketplace",
        "Vital Assistant"
    ]
    property var bodies: [
        "Graphite, ivory, and champagne. The artwork is original.",
        "Inter on the desktop. Dark by default. The accent stays champagne.",
        "Install and remove applications. Packages are checked with SHA-256.",
        "Ask for a command. It runs only after you confirm. Keys stay in the keyring."
    ]

    Timer {
        interval: 6500
        running: true
        repeat: true
        onTriggered: {
            card.opacity = 0.35
            root.slide = (root.slide + 1) % 4
            fadeIn.start()
        }
    }

    Rectangle {
        id: card
        anchors.centerIn: parent
        anchors.verticalCenterOffset: -12
        width: Math.min(parent.width - 80, 560)
        height: 280
        radius: 22
        color: "#141820"
        border.color: "#C6A56A"
        border.width: 1

        Image {
            id: mark
            source: "logo.png"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 28
            width: 72
            height: 72
            fillMode: Image.PreserveAspectFit
        }

        Text {
            id: heading
            anchors.top: mark.bottom
            anchors.topMargin: 18
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.titles[root.slide]
            color: "#F6F1E7"
            font.pixelSize: 28
            font.family: "Inter"
        }

        Text {
            id: copy
            anchors.top: heading.bottom
            anchors.topMargin: 12
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 36
            anchors.rightMargin: 36
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: root.bodies[root.slide]
            color: "#C9C2B4"
            font.pixelSize: 16
            font.family: "Inter"
        }
    }

    NumberAnimation {
        id: fadeIn
        target: card
        property: "opacity"
        to: 1
        duration: 280
    }

    Row {
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 72
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 10
        Repeater {
            model: 4
            Rectangle {
                width: index === root.slide ? 22 : 8
                height: 8
                radius: 4
                color: index === root.slide ? "#C6A56A" : "#3A342C"
                Behavior on width { NumberAnimation { duration: 180 } }
            }
        }
    }

    Text {
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28
        anchors.horizontalCenter: parent.horizontalCenter
        text: "Vital OS @VERSION@    ·    based on Ubuntu 24.04 LTS"
        color: "#C6A56A"
        font.pixelSize: 14
        font.family: "Inter"
    }

    Component.onCompleted: fadeIn.start()
}
