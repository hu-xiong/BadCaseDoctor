package com.farm.calculator.controller;

import com.farm.calculator.model.CropType;
import com.farm.calculator.model.Plantation;
import com.farm.calculator.model.User;
import com.farm.calculator.service.PlantationService;
import com.farm.calculator.service.UserService;
import com.farm.calculator.service.WaterCalculatorService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;

@Controller
public class FarmController {

    @Autowired
    private PlantationService plantationService;

    @Autowired
    private UserService userService;

    @Autowired
    private WaterCalculatorService calculatorService;

    private User getCurrentUser(Authentication auth) {
        return userService.findByEmail(auth.getName());
    }

    @GetMapping("/")
    public String index(Authentication auth, Model model) {
        User user = getCurrentUser(auth);
        List<Plantation> plantations = plantationService.getUserPlantations(user);

        model.addAttribute("cropTypes", CropType.values());
        model.addAttribute("plantations", plantations);
        model.addAttribute("now", LocalDateTime.now());
        return "index";
    }

    @PostMapping("/plant")
    public String plant(@RequestParam("cropType") String cropTypeName,
                        @RequestParam("sowingTime") String sowingTimeStr,
                        Authentication auth, Model model) {
        try {
            User user = getCurrentUser(auth);
            LocalDateTime sowingTime = LocalDateTime.parse(sowingTimeStr, DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm"));
            plantationService.createPlantation(user, cropTypeName, sowingTime);
        } catch (Exception e) {
            model.addAttribute("error", "播种失败：" + e.getMessage());
        }
        return "redirect:/";
    }

    @PostMapping("/water/{id}")
    public String water(@PathVariable Long id, Authentication auth) {
        try {
            User user = getCurrentUser(auth);
            plantationService.water(id, user);
        } catch (Exception e) {
            // ignore
        }
        return "redirect:/";
    }

    @PostMapping("/harvest/{id}")
    public String harvest(@PathVariable Long id, Authentication auth) {
        try {
            User user = getCurrentUser(auth);
            plantationService.harvest(id, user);
        } catch (Exception e) {
            // ignore
        }
        return "redirect:/";
    }

    @GetMapping("/schedule")
    @ResponseBody
    public List<LocalDateTime> getSchedule(@RequestParam("cropType") String cropTypeName,
                                            @RequestParam("sowingTime") String sowingTimeStr) {
        CropType cropType = CropType.valueOf(cropTypeName);
        LocalDateTime sowingTime = LocalDateTime.parse(sowingTimeStr, DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm"));
        return calculatorService.getWateringSchedule(cropType, sowingTime);
    }
}
