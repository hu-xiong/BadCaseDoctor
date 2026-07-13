package com.farm.calculator.controller;

import com.farm.calculator.model.User;
import com.farm.calculator.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class ProfileController {

    @Autowired
    private UserService userService;

    @GetMapping("/profile")
    public String profile(Authentication auth, Model model) {
        User user = userService.findByEmail(auth.getName());
        model.addAttribute("user", user);
        return "profile";
    }

    @PostMapping("/profile")
    public String updateProfile(@RequestParam(value = "qq", required = false) String qq,
                                @RequestParam(value = "wechat", required = false) String wechat,
                                @RequestParam(value = "emailNotify", defaultValue = "true") boolean emailNotify,
                                Authentication auth, Model model) {
        try {
            User user = userService.findByEmail(auth.getName());
            user.setQq(qq);
            user.setWechat(wechat);
            user.setEmailNotify(emailNotify);
            userService.updateProfile(user);
            model.addAttribute("success", "资料已更新");
        } catch (Exception e) {
            model.addAttribute("error", e.getMessage());
        }
        User user = userService.findByEmail(auth.getName());
        model.addAttribute("user", user);
        return "profile";
    }
}
