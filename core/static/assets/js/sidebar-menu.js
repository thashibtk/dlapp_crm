(function ($) {
  $(".toggle-nav").click(function () {
    $("#sidebar-links .nav-menu").css("left", "0px");
  });
  $(".mobile-back").click(function () {
    $("#sidebar-links .nav-menu").css("left", "-410px");
  });
  $(".page-wrapper").attr(
    "class",
    "page-wrapper " + localStorage.getItem("page-wrapper-Zono")
  );
  if (localStorage.getItem("page-wrapper-Zono") === null) {
    $(".page-wrapper").addClass("compact-wrapper");
  }

  // left sidebar and vertical menu
  if ($("#pageWrapper").hasClass("compact-wrapper")) {
    jQuery(".sidebar-title").append(
      '<div class="according-menu"><i class="fa fa-angle-right"></i></div>'
    );

    // Accordion sidebar (only one open at a time on click)
    jQuery(".sidebar-title").click(function (e) {
       var $this = $(this);

      // ✅ if this has a submenu, prevent default (accordion behavior)
      if ($this.next(".sidebar-submenu").length) {
        e.preventDefault();
      } else {
        // ✅ no submenu, let it navigate normally
        return true;
      }

      var group = $this.data("group");

      if ($this.next().is(":hidden") === true) {
        // close all
        $(".sidebar-title").removeClass("active").find("div.according-menu")
          .replaceWith('<div class="according-menu"><i class="fa fa-angle-right"></i></div>');
        $(".sidebar-submenu, .menu-content").slideUp("normal");

        // open clicked one
        $this.addClass("active");
        $this.find("div.according-menu").replaceWith(
          '<div class="according-menu"><i class="fa fa-angle-down"></i></div>'
        );
        $this.next().slideDown("normal");

        if (group) {
          localStorage.setItem("sidebar-open-group", group);
        }
      } else {
        // collapse clicked one
        $this.removeClass("active");
        $this.find("div.according-menu").replaceWith(
          '<div class="according-menu"><i class="fa fa-angle-right"></i></div>'
        );
        $this.next().slideUp("normal");
        localStorage.removeItem("sidebar-open-group");
      }
    });

    // hide all submenus unless they contain an active li
    jQuery(".sidebar-submenu, .menu-content").each(function () {
      if (!$(this).find("li.active").length) {
        $(this).hide();
      } else {
        var parentTitle = $(this).prev(".sidebar-title");
        parentTitle.addClass("active");
        parentTitle.find("div.according-menu")
          .replaceWith('<div class="according-menu"><i class="fa fa-angle-down"></i></div>');
        $(this).show();
      }
    });
  }

  // toggle sidebar
  $nav = $(".sidebar-wrapper");
  $header = $(".page-header");
  $toggle_nav_top = $(".toggle-sidebar");
  $toggle_nav_top.click(function () {
    $nav.toggleClass("close_icon");
    $header.toggleClass("close_icon");
    $(window).trigger("overlay");
  });

  $(window).on("overlay", function () {
    $bgOverlay = $(".bg-overlay");
    $isHidden = $nav.hasClass("close_icon");
    if ($(window).width() <= 1184 && !$isHidden && $bgOverlay.length === 0) {
      $('<div class="bg-overlay active"></div>').appendTo($("body"));
    }
    if ($isHidden && $bgOverlay.length > 0) {
      $bgOverlay.remove();
    }
  });

  $(".sidebar-wrapper .back-btn").on("click", function (e) {
    $(".page-header").toggleClass("close_icon");
    $(".sidebar-wrapper").toggleClass("close_icon");
    $(window).trigger("overlay");
  });

  $("body").on("click", ".bg-overlay", function () {
    $header.addClass("close_icon");
    $nav.addClass("close_icon");
    $(this).remove();
  });

  $body_part_side = $(".body-part");
  $body_part_side.click(function () {
    $toggle_nav_top.attr("checked", false);
    $nav.addClass("close_icon");
    $header.addClass("close_icon");
  });

  // responsive sidebar
  var $window = $(window);
  var widthwindow = $window.width();
  (function ($) {
    "use strict";
    if (widthwindow <= 1184) {
      $toggle_nav_top.attr("checked", false);
      $nav.addClass("close_icon");
      $header.addClass("close_icon");
    }
  })(jQuery);
  $(window).resize(function () {
    var widthwindaw = $window.width();
    if (widthwindaw <= 1184) {
      $toggle_nav_top.attr("checked", false);
      $nav.addClass("close_icon");
      $header.addClass("close_icon");
    } else {
      $toggle_nav_top.attr("checked", true);
      $nav.removeClass("close_icon");
      $header.removeClass("close_icon");
    }
  });

  // horizontal arrows
  var view = $("#sidebar-menu");
  var move = "500px";
  var leftsideLimit = -500;

  var getMenuWrapperSize = function () {
    return $(".sidebar-wrapper").innerWidth();
  };
  var menuWrapperSize = getMenuWrapperSize();

  if (menuWrapperSize >= "1660") {
    var sliderLimit = -3000;
  } else if (menuWrapperSize >= "1440") {
    var sliderLimit = -3600;
  } else {
    var sliderLimit = -4200;
  }

  $("#left-arrow").addClass("disabled");
  $("#right-arrow").click(function () {
    var currentPosition = parseInt(view.css("marginLeft"));
    if (currentPosition >= sliderLimit) {
      $("#left-arrow").removeClass("disabled");
      view.stop(false, true).animate(
        { marginLeft: "-=" + move },
        { duration: 400 }
      );
      if (currentPosition == sliderLimit) {
        $(this).addClass("disabled");
      }
    }
  });

  $("#left-arrow").click(function () {
    var currentPosition = parseInt(view.css("marginLeft"));
    if (currentPosition < 0) {
      view.stop(false, true).animate(
        { marginLeft: "+=" + move },
        { duration: 400 }
      );
      $("#right-arrow").removeClass("disabled");
      $("#left-arrow").removeClass("disabled");
      if (currentPosition >= leftsideLimit) {
        $(this).addClass("disabled");
      }
    }
  });

  // Highlight active link only (accordion mode)
  function setActiveMenuItem() {
    var current = window.location.pathname;
    if (current.endsWith("/") && current.length > 1) {
      current = current.slice(0, -1);
    }

    var matched = false;

    $(".sidebar-wrapper nav ul li a").each(function () {
      var link = $(this).attr("href");
      if (link && link !== "#") {
        var cleanLink = link.endsWith("/") ? link.slice(0, -1) : link;
        if (current === cleanLink) {
          matched = true;

          $(".sidebar-wrapper nav").find("a").removeClass("active");
          $(".sidebar-wrapper nav").find("li").removeClass("active");
          $(".sidebar-title").removeClass("active");
          $(".sidebar-submenu").slideUp(0);

          $(this).addClass("active");
          $(this).parents("li").addClass("active");

          var submenu = $(this).closest(".sidebar-submenu");
          if (submenu.length) {
            submenu.slideDown(0);
            var parentTitle = submenu.prev(".sidebar-title");
            parentTitle.addClass("active");
            parentTitle.find("div.according-menu")
              .replaceWith('<div class="according-menu"><i class="fa fa-angle-down"></i></div>');
          }
          return false;
        }
      }
    });

    // ⚠️ if no match (like Products page), don’t collapse user toggle
    if (!matched) {
      return;
    }
  }

  $(document).ready(function () {
    setActiveMenuItem();

    var lastOpen = localStorage.getItem("sidebar-open-group");
    if (lastOpen) {
      var $title = $('.sidebar-title[data-group="' + lastOpen + '"]');
      if ($title.length) {
        $title.addClass("active");
        $title.find("div.according-menu").replaceWith(
          '<div class="according-menu"><i class="fa fa-angle-down"></i></div>'
        );
        $title.next().show();
      }
    }
  });

  $(window).on("popstate", function () {
    setActiveMenuItem();
  });

  // Function to manually set active state (accordion mode)
  window.setActiveMenuByUrl = function (urlName) {
    $(".sidebar-wrapper nav").find("a").removeClass("active");
    $(".sidebar-wrapper nav").find("li").removeClass("active");
    $(".sidebar-title").removeClass("active");

    // close all before opening
    $(".sidebar-submenu").slideUp(0);
    $(".sidebar-title .according-menu")
      .replaceWith('<div class="according-menu"><i class="fa fa-angle-right"></i></div>');

    $(".sidebar-wrapper nav ul li a").each(function () {
      var href = $(this).attr("href");
      if (href && href.includes(urlName)) {
        $(this).addClass("active");
        $(this).parents("li").first().addClass("active");

        var parentSubmenu = $(this).closest(".sidebar-submenu");
        if (parentSubmenu.length) {
          parentSubmenu.slideDown(0);
          var parentTitle = parentSubmenu.prev(".sidebar-title");
          parentTitle.addClass("active");
          parentTitle.find("div.according-menu")
            .replaceWith('<div class="according-menu"><i class="fa fa-angle-down"></i></div>');
        }
        return false;
      }
    });
  };

  // --- other menu behaviors remain unchanged ---
  $(".left-header .mega-menu .nav-link").on("click", function (event) {
    event.stopPropagation();
    $(this).parent().children(".mega-menu-container").toggleClass("show");
  });

  $(".left-header .level-menu .nav-link").on("click", function (event) {
    event.stopPropagation();
    $(this).parent().children(".header-level-menu").toggleClass("show");
  });

  $(document).click(function () {
    $(".mega-menu-container").removeClass("show");
    $(".header-level-menu").removeClass("show");
  });

  $(window).scroll(function () {
    var scroll = $(window).scrollTop();
    if (scroll >= 50) {
      $(".mega-menu-container").removeClass("show");
      $(".header-level-menu").removeClass("show");
    }
  });

  $(".left-header .level-menu .nav-link").click(function () {
    if ($(".mega-menu-container").hasClass("show")) {
      $(".mega-menu-container").removeClass("show");
    }
  });

  $(".left-header .mega-menu .nav-link").click(function () {
    if ($(".header-level-menu").hasClass("show")) {
      $(".header-level-menu").removeClass("show");
    }
  });

  $(document).ready(function () {
    $(".outside").click(function () {
      $(this).find(".menu-to-be-close").slideToggle("fast");
    });
  });
  $(document).on("click", function (event) {
    var $trigger = $(".outside");
    if ($trigger !== event.target && !$trigger.has(event.target).length) {
      $(".menu-to-be-close").slideUp("fast");
    }
  });

  $(".left-header .link-section > div").on("click", function (e) {
    if ($(window).width() <= 1199) {
      $(".left-header .link-section > div").removeClass("active");
      $(this).toggleClass("active");
      $(this).parent().children("ul").toggleClass("d-block").slideToggle();
    }
  });

  if ($(window).width() <= 1199) {
    $(".left-header .link-section").children("ul").css("display", "none");
    $(this).parent().children("ul").toggleClass("d-block").slideToggle();
  }

  if (
    $(".simplebar-wrapper .simplebar-content-wrapper") &&
    $("#pageWrapper").hasClass("compact-wrapper")
  ) {
    var activeLink = $(".simplebar-wrapper .simplebar-content-wrapper a.active");
    if (activeLink.length > 0) {
      $(".simplebar-wrapper .simplebar-content-wrapper").animate(
        { scrollTop: activeLink.offset().top - 400 },
        1000
      );
    }
  }
})(jQuery);
