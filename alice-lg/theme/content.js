Alice.updateContent({
    header: {
        title: "",
        tagline: ""
    },
    welcome: {
        title: "IIX-JI Looking Glass",
        tagline: "BGP Looking Glass for IIX-JI Networks"
    },
    /**lookup: {
        examples: [["asn", "AS51531"], ["community", 65535, 666], ["community", 65001, 0], ["community", 6695, 1911, 124], ["prefix", "46.31.120.0/21"], ["community", 6695, 1101, 13], ["community", 65200, 65212], ["q", "DE-CIX Academy"], ["community", 65535, 0], ["community", 6695, 1913, 276], ["community", 6695, 1001, 1], ["community", "rt", 6695, 4200000001], ["community", 6695, 1101, 3], ["q", "DE-CIX"], ["community", 196610, 9999, 9999], ["community", 6695, 1912, 1]]
      },
      footer: "<center>" +
        "<a href='https://www.de-cix.net/imprint'>Imprint</a> &middot; " +
        "<a href='https://www.de-cix.net/terms-and-conditions'>Terms and Conditions</a> &middot; " +
        "<a href='https://www.de-cix.net/privacy-policy'>Privacy Policy</a>    </center>"*/
    lookup: {
        examples: [
            ["asn", "AS24521"],
            ["prefix", "123.255.202.0/24"],
            ["community", 65535, 666],
            ["community", 65520, 13],
            ["q", "Data"]
        ]
    },
    footer: "" +
    "<p style='margin-left:15px'>&copy; 2025 <a style='font-size:14px !important' href='https://ji.iix.net.id/' target='_blank'>IIX Jatim</a> | Powered by <a style='font-size:14px !important' href='https://github.com/alice-lg/alice-lg' target='_blank'>AliceLG</a></p>"
    });

    Alice.onLayoutReady(function(page) {
        // page is the layout HTML root element
        
    });
    
    document.title = "IIX-JI Looking Glass";