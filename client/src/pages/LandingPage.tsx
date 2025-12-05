import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ChatWidget } from "@/components/ChatWidget";
import { Calculator } from "@/components/Calculator";
import { InlineStateSelector } from "@/components/InlineStateSelector";
import { 
  CheckCircle2, 
  Car, 
  DollarSign, 
  ShieldCheck, 
  Briefcase, 
  Clock, 
  ArrowRight,
  Menu,
  Phone,
  MessageCircle
} from "lucide-react";
import { motion } from "framer-motion";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "@/components/ui/carousel";
import generatedImage from '@assets/generated_images/professional_modern_pickup_truck_on_a_clean_open_road.png';
import headerLogo from '@assets/sears_header_logo_250_1764519439419.png';
import fullLogo from '@assets/Sears-Home-Services-logo_1764519439419.jpg';

type State = "CA" | "WA" | "IL" | "OTHER" | null;

export default function LandingPage() {
  const [selectedState, setSelectedState] = useState<State>(null);
  const ratePerMile = selectedState === null ? null : (["CA", "WA", "IL"].includes(selectedState) ? 0.70 : 0.57);

  const scrollToEnroll = () => {
    const element = document.getElementById('enroll');
    if (element) element.scrollIntoView({ behavior: 'smooth' });
  };

  const scrollToCalculator = () => {
    const element = document.getElementById('calculator');
    if (element) element.scrollIntoView({ behavior: 'smooth' });
  };

  const handleEnrollClick = () => {
    // Open the enrollment app via proxy route
    window.open('/enroll', '_blank');
  };

  const handleAdminClick = () => {
    // Open the admin dashboard via proxy route
    window.open('/admin', '_blank');
  };

  return (
    <div className="min-h-screen bg-background font-sans">
      {/* Navigation */}
      <nav className="sticky top-0 z-40 w-full bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b border-border/40">
        <div className="container mx-auto flex h-16 items-center justify-between px-4 md:px-8">
          <div className="flex items-center gap-3">
            <img src={headerLogo} alt="Sears Home Services" className="h-10" />
            <span className="font-bold text-xs tracking-wider text-muted-foreground hidden sm:inline-block uppercase">BYOV Program</span>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden md:flex items-center gap-6 text-sm font-medium text-muted-foreground">
              <a href="#benefits" className="hover:text-primary transition-colors">Benefits</a>
              <a href="#calculator" className="hover:text-primary transition-colors">Calculator</a>
              <a href="#testimonials" className="hover:text-primary transition-colors">Testimonials</a>
            </div>
            <Button onClick={handleAdminClick} variant="outline" className="font-semibold">
              Admin
            </Button>
            <Button onClick={handleEnrollClick} className="bg-primary hover:bg-primary/90 text-white font-semibold shadow-md">
              Enroll Now
            </Button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-20 pb-32 md:pt-32 md:pb-48 overflow-hidden">
        <div className="absolute inset-0 z-0">
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/90 to-transparent z-10" />
          <img 
            src={generatedImage} 
            alt="Technician truck on road" 
            className="w-full h-full object-cover opacity-40"
          />
        </div>
        
        <div className="container mx-auto relative z-20 px-4 md:px-8">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="max-w-3xl space-y-6"
          >
            <div className="inline-flex items-center rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-sm font-medium text-primary backdrop-blur-sm">
              <span className="flex h-2 w-2 rounded-full bg-primary mr-2 animate-pulse"></span>
              New: $400 Sign-On Bonus Available
            </div>
            <h1 className="text-4xl md:text-6xl lg:text-7xl font-heading font-bold tracking-tight text-foreground leading-[1.1]">
              Drive Your Own Vehicle. <br />
              <span className="text-primary">Earn More.</span>
            </h1>
            <p className="text-xl md:text-2xl text-muted-foreground max-w-2xl leading-relaxed">
              The BYOV program pays you back for your gas, maintenance, and insurance—and puts extra cash in your pocket every week.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 pt-4">
              <Button size="lg" onClick={scrollToEnroll} className="bg-primary hover:bg-primary/90 text-lg h-14 px-8 shadow-lg shadow-primary/20">
                Get Started <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
              <Button size="lg" onClick={scrollToCalculator} variant="outline" className="h-14 px-8 text-lg bg-background/50 backdrop-blur-sm hover:bg-background/80">
                Calculate Earnings
              </Button>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Benefits Grid */}
      <section id="benefits" className="py-24 bg-muted/30">
        <div className="container mx-auto px-4 md:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <h2 className="text-3xl md:text-4xl font-heading font-bold mb-4">Why Switch to BYOV?</h2>
            <p className="text-lg text-muted-foreground mb-6">Join the growing number of technicians who have upgraded their comfort and paycheck by driving their own Truck, Van, Car, or SUV.</p>
            <div className="flex justify-center">
              <InlineStateSelector 
                selectedState={selectedState} 
                onStateChange={setSelectedState}
              />
            </div>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              {
                icon: DollarSign,
                title: ratePerMile !== null ? `$${ratePerMile.toFixed(2)} Per Mile` : "Select State for Rate",
                desc: ratePerMile !== null 
                  ? "Tax-free reimbursement paid weekly. Covers gas, maintenance, and puts profit in your pocket."
                  : "Choose your state above to see your mileage reimbursement rate.",
                color: "text-accent"
              },
              {
                icon: Car,
                title: "Any Vehicle Type",
                desc: "Trucks, Vans, Cars, and SUVs are all welcome (2005+ preferred). Unsure if your vehicle qualifies? Just ask!",
                color: "text-primary"
              },
              {
                icon: ShieldCheck,
                title: "Extra Safety",
                desc: "Sears provides excess liability coverage while you are on company business.",
                color: "text-primary"
              },
              {
                icon: Clock,
                title: "Save Time",
                desc: "Clock out and go straight to personal errands. No need to swap vehicles at the end of the day.",
                color: "text-primary"
              },
              {
                icon: Briefcase,
                title: "Professional Image",
                desc: "Customers appreciate a clean, modern vehicle. It signals professionalism before you even knock-just be sure to always be in uniform and equipped to tackle the repair.",
                color: "text-primary"
              },
              {
                icon: CheckCircle2,
                title: "Rental Support",
                desc: "We've got your back with up to 5 days/year of rental car support for unplanned breakdowns.",
                color: "text-primary"
              }
            ].map((feature, i) => (
              <motion.div
                key={i}
                whileHover={{ y: -5 }}
                className="bg-card border border-border/50 p-8 rounded-2xl shadow-sm hover:shadow-md transition-all"
              >
                <div className={`h-12 w-12 rounded-lg bg-muted flex items-center justify-center mb-6 ${feature.color}`}>
                  <feature.icon className="h-6 w-6" />
                </div>
                <h3 className="text-xl font-bold mb-3">{feature.title}</h3>
                <p className="text-muted-foreground leading-relaxed">{feature.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Calculator Section */}
      <section id="calculator" className="py-24 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-primary/20 to-transparent" />
        <div className="container mx-auto px-4 md:px-8">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <div className="space-y-6">
              <h2 className="text-3xl md:text-5xl font-heading font-bold leading-tight">
                Visualize Your <br />
                <span className="text-primary">Mileage Payout</span>
              </h2>
              <p className="text-lg text-muted-foreground leading-relaxed">
                {ratePerMile !== null 
                  ? `Most technicians find that the $${ratePerMile.toFixed(2)}/mile reimbursement covers significantly more than just gas. Use the calculator to see how much you could be earning weekly based on your route and vehicle.`
                  : "Select your state to see your mileage rate. Use the calculator to see how much you could be earning weekly based on your route and vehicle."
                }
              </p>
              <ul className="space-y-4 pt-4">
                <li className="flex items-center gap-3">
                  <div className="h-6 w-6 rounded-full bg-accent/20 flex items-center justify-center text-accent">
                    <CheckCircle2 className="h-4 w-4" />
                  </div>
                  <span className="font-medium">Paid Weekly</span>
                </li>
                <li className="flex items-center gap-3">
                  <div className="h-6 w-6 rounded-full bg-accent/20 flex items-center justify-center text-accent">
                    <CheckCircle2 className="h-4 w-4" />
                  </div>
                  <span className="font-medium">Tax-Free Reimbursement</span>
                </li>
                <li className="flex items-center gap-3">
                  <div className="h-6 w-6 rounded-full bg-accent/20 flex items-center justify-center text-accent">
                    <CheckCircle2 className="h-4 w-4" />
                  </div>
                  <span className="font-medium">Average weekly payout of approx $407.25</span>
                </li>
              </ul>
            </div>
            <div className="relative z-10">
              <div className="absolute -inset-4 bg-primary/5 rounded-3xl blur-2xl -z-10" />
              <Calculator 
                ratePerMile={ratePerMile} 
                selectedState={selectedState}
                onStateChange={setSelectedState}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section id="testimonials" className="py-24 bg-primary text-primary-foreground relative">
        <div className="container mx-auto px-4 md:px-8 relative z-10">
          <h2 className="text-3xl md:text-4xl font-heading font-bold text-center mb-16">What Techs Are Saying</h2>
          
          <Carousel
            opts={{
              align: "start",
              loop: true,
            }}
            className="w-full max-w-6xl mx-auto"
          >
            <CarouselContent className="-ml-4">
              {[
                {
                  quote: "I'm more comfortable in my truck with tilt wheel and cruise control, and it's nice to be able to transition straight into personal time after my last call.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "Customers are happy to see me pull up because they know I mean business. My vehicle is much cleaner and customers compliment me on it all the time.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "The reimbursement is enough to cover all the costs of a modest vehicle with average fuel economy. Just the phrase 'let Sears buy a vehicle for you' says it all.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "It allows me to be more comfortable day to day on the job and makes the transition to personal time much easier. Much easier to manage tools with my own layout too.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "The program has been a tremendous help financially. I'm in the comfort of my own ride and have everything organized exactly how I need it.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "It's made everything a lot easier. The mileage submission process is straightforward, and it's better than having to get a rental. Plus, customers appreciate seeing a well-maintained vehicle pull up.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "Customers are happy to see me pull up because they know I mean business. My vehicle is much cleaner and customers compliment me on it all the time. Compared to showing up in a dirty van, now no one even asks what company I work for.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "After paying for gas, I've made back enough to cover needed repairs, as well as saving towards a newer vehicle. The weekly payout really helps get the bills paid on time and reduces stress financially.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "I don't have to worry about my car breaking down like I did with the vans. Plus, it's extra money I could really use for personal expenses.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "The pay is great for this program and it makes my life easier. My vehicle is comfortable, reliable, and I have everything organized exactly how I need it.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "The reimbursement appears to be enough to cover all the costs of a modest vehicle with average fuel economy. It's essentially letting Sears buy a vehicle for you by paying you to drive your own.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "I would have left Transformco over the cameras, this allows me to continue my employment with the company. Huge advantage to not be micromanaged by big brother.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "Parking at home is easier. Once I did it the first time [submitting miles] it was easier. It covers the insurance cost of vehicle.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "Better organization, better time usage of my personal time, extra income. Helping to pay my vehicle.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "Having vehicle maintenance come from a dedicated payment rather than my paycheck has been a genuine benefit. It has made work much smoother and is very convenient.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "I feel more comfortable and excited then I have a vehicle that I can trust. Earning a little bit more money is also helpful paying for the bills.",
                  author: "Current BYOV Participant"
                },
                {
                  quote: "Advantages are driving better car and getting some extra on our budget. Big point is no camera.",
                  author: "Current BYOV Participant"
                }
              ].map((t, i) => (
                <CarouselItem key={i} className="pl-4 md:basis-1/2 lg:basis-1/3">
                  <div className="bg-primary-foreground/10 backdrop-blur-md border border-primary-foreground/10 p-8 rounded-2xl h-full flex flex-col">
                    <div className="mb-6 text-primary-foreground/40">
                      <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M14.017 21L14.017 18C14.017 16.8954 14.9124 16 16.017 16H19.017C19.5693 16 20.017 15.5523 20.017 15V9C20.017 8.44772 19.5693 8 19.017 8H15.017C14.4647 8 14.017 8.44772 14.017 9V11C14.017 11.5523 13.5693 12 13.017 12H12.017V5H22.017V15C22.017 18.3137 19.3307 21 16.017 21H14.017ZM5.0166 21L5.0166 18C5.0166 16.8954 5.91203 16 7.0166 16H10.0166C10.5689 16 11.0166 15.5523 11.0166 15V9C11.0166 8.44772 10.5689 8 10.0166 8H6.0166C5.46432 8 5.0166 8.44772 5.0166 9V11C5.0166 11.5523 4.56889 12 4.0166 12H3.0166V5H13.0166V15C13.0166 18.3137 10.3303 21 7.0166 21H5.0166Z" />
                      </svg>
                    </div>
                    <p className="text-lg font-medium leading-relaxed mb-6 italic flex-grow">"{t.quote}"</p>
                    <p className="text-sm font-bold uppercase tracking-wider opacity-70">- {t.author}</p>
                  </div>
                </CarouselItem>
              ))}
            </CarouselContent>
            <div className="flex justify-center gap-4 mt-8">
              <CarouselPrevious className="static translate-y-0 bg-primary-foreground/10 border-primary-foreground/20 text-primary-foreground hover:bg-primary-foreground/20 hover:text-white" />
              <CarouselNext className="static translate-y-0 bg-primary-foreground/10 border-primary-foreground/20 text-primary-foreground hover:bg-primary-foreground/20 hover:text-white" />
            </div>
          </Carousel>
        </div>
      </section>

      {/* CTA / Enroll Section */}
      <section id="enroll" className="py-24 bg-background">
        <div className="container mx-auto px-4 md:px-8">
          <div className="bg-muted rounded-3xl p-8 md:p-16 text-center border border-border/50 shadow-sm">
            <h2 className="text-3xl md:text-4xl font-heading font-bold mb-6">Ready to Get Started?</h2>
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-10">
              Enrollment is simple. Join the program today and start earning mileage reimbursement on your next route.
            </p>
            <div className="flex flex-col items-center gap-6">
              <Button size="lg" onClick={handleEnrollClick} className="bg-primary hover:bg-primary/90 text-white text-lg h-16 px-12 rounded-full shadow-xl hover:shadow-2xl transition-all transform hover:-translate-y-1">
                Open Enrollment App
              </Button>
              <div className="flex flex-col md:flex-row items-center gap-6 text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Phone className="h-4 w-4" />
                  <span>Questions? Call Tyler Morgan at <strong className="text-foreground">910-906-3588</strong></span>
                </div>
                <div className="hidden md:block h-4 w-px bg-border" />
                <div className="flex items-center gap-2">
                  <MessageCircle className="h-4 w-4" />
                  <span>Or ask our <strong className="text-primary">AI Assistant</strong> in the bottom right</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <footer className="bg-card border-t border-border py-12">
        <div className="container mx-auto px-4 md:px-8 flex flex-col md:flex-row justify-between items-center gap-6">
          <img src={fullLogo} alt="Sears Home Services" className="h-16" />
          <p className="text-sm text-muted-foreground text-center md:text-right">
            © 2025 Sears Home Services. All rights reserved. BYOV Policy Effective 8/1/2025.
          </p>
        </div>
      </footer>

      <ChatWidget state={selectedState} />
    </div>
  );
}
